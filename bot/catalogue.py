"""Telegram-independent source rendering; no LLM or Telegram API needed."""
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
from bot.prompts import academic_note, DEFAULT_ACADEMIC_YEAR
from bot.timetable import Timetable
from ingestion.bge_embeddings import index_for_provider, load_environment

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'datafiles/academic'
SYLLABUS_PDF = 'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_syll_22.pdf'


def link(label, url):
    if not isinstance(url, str) or urlparse(url).scheme not in ('https', 'http'):
        return escape(label)
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def topic_query(text):
    """Keep the full syllabus-topic context within the retriever's 1,000-char limit."""
    return ' '.join(str(text).split())[:900]


class Catalogue:
    def __init__(self):
        self.courses = json.loads((DATA/'course_catalogue.json').read_text(encoding='utf-8'))
        self.timetable = Timetable()
        self.syllabi = {s['syllabus_id']:s for s in json.loads((DATA/'syllabus_courses.json').read_text(encoding='utf-8'))}
        self.faculty = {f['faculty_id']:f for f in json.loads((DATA/'faculty_profiles.json').read_text(encoding='utf-8'))}
        self.projects = {p['project_id']:p for p in json.loads((DATA/'department_projects.json').read_text(encoding='utf-8'))}
        self.books = {}
        for book in json.loads((DATA/'book_contents.json').read_text(encoding='utf-8')):
            for chapter in book['chapters']:
                if chapter.get('review_status') != 'source_label_requires_review':
                    self.books[chapter['chapter_id']] = (book, chapter)
        self.book_references = json.loads((DATA/'book_references.json').read_text(encoding='utf-8'))
        self.book_references_by_id = {item['resource_id']:item for item in self.book_references}
        self.lectures = {}
        for course in json.loads((DATA/'nptel_references.json').read_text(encoding='utf-8')):
            for lesson in course['lessons']:
                self.lectures[f"{course['resource_id']}:{lesson['unit_id']}:{lesson['lesson_id']}"] = (course, lesson)
        self.topic_resources = {}
        topic_map_path=DATA/'topic_resource_map.json'
        load_environment()
        index_path=index_for_provider(os.getenv('SIGNAL_EMBEDDING_PROVIDER','huggingface').strip().lower())
        if topic_map_path.exists() and index_path.exists():
            try:
                topic_map=json.loads(topic_map_path.read_text(encoding='utf-8'))
                chunks_hash=hashlib.sha256((DATA/'embedding_chunks.jsonl').read_bytes()).hexdigest()
                with sqlite3.connect(f'{index_path.resolve().as_uri()}?mode=ro',uri=True) as db:
                    active=json.loads(db.execute('SELECT value FROM manifest WHERE id=1').fetchone()[0])
                map_manifest=topic_map.get('manifest',{})
                if (map_manifest.get('chunk_source_sha256')==chunks_hash
                        and map_manifest.get('embedding')==active.get('embedding')):
                    self.topic_resources={c['curriculum_code']:c for c in topic_map.get('courses',[])}
            except (OSError,ValueError,KeyError,TypeError):
                self.topic_resources={}

    def semesters(self, course):
        return sorted({e['semester'] for e in course['curriculum_entries'] if e.get('semester')})

    def year_courses(self, year):
        if str(year) not in ('1','2','3','4','options'):
            raise ValueError('Choose year 1, 2, 3, 4 or options')
        rows = [c for c in self.courses if (not self.semesters(c) if year=='options' else
            any((s+1)//2==int(year) for s in self.semesters(c)))]
        return sorted(rows,key=lambda c:(min(self.semesters(c),default=99),c['code'].casefold()))

    def course(self, code):
        normalized = re.sub(r'[^A-Z0-9]', '', code.upper())
        return next((c for c in self.courses if re.sub(r'[^A-Z0-9]', '', c['code'].upper())==normalized),None)

    def course_details(self, course, academic_year=DEFAULT_ACADEMIC_YEAR):
        semesters = self.semesters(course)
        credit_values=[e.get('credits_raw') for e in course['curriculum_entries'] if e.get('credits_raw')]
        credit_values += [r.get('credits_raw') for r in course.get('workbook_records',[]) if r.get('credits_raw')]
        credits = ' / '.join(dict.fromkeys(credit_values))
        entry = next(iter(course['curriculum_entries']),None)
        evidence = entry.get('evidence',{}) if entry else {}
        if not evidence and course.get('workbook_records'):
            evidence = course['workbook_records'][0]['evidence']
        page = evidence.get('page')
        source_lines=[]
        if evidence.get('path') == 'data/btech_ec_str_24.pdf' and page:
            source_lines.append(link(f'Curriculum · page {page}',
                'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_str_24.pdf#page='+str(page)))
        elif evidence.get('path','').endswith('.xlsx'):
            source_lines.append(escape(f"Source: ECE_Course_Structure.xlsx · {evidence.get('sheet')} row {evidence.get('row')}"))
        for workbook_record in course.get('workbook_records',[]):
            item=workbook_record['evidence']
            label=escape(f"Workbook: {item['sheet']} row {item['row']}")
            if label not in source_lines: source_lines.append(label)
            if len(source_lines)>=4: break
        source_line='\n'.join(source_lines) or 'Course source is not recorded.'
        faculty_line=self.course_faculty_details(course,missing_message=False)
        instructor_line='\n'+faculty_line if faculty_line else ''
        return f"<b>{escape(course['code'])} · {escape(course['title'])}</b>\n" + \
            f"Semester: {', '.join(map(str,semesters)) if semesters else 'not assigned (elective / option)'}\n" + \
            f"Credits: {escape(credits or 'not stated')}\n" + source_line + \
            instructor_line + \
            '\n'+academic_note(academic_year) + \
            '\n\nUse this course as a filter, then send a study topic.'

    def course_title(self, code):
        course = self.course(code)
        return course['title'] if course else None

    def course_faculty_details(self, course, *, missing_message=True):
        assignments=course.get('faculty_assignments',[])
        if not assignments:
            return (f"No professor is recorded in the supplied data for {escape(course['code'])}. "
                    "I won’t guess a teaching assignment.") if missing_message else ''
        lines=[]
        for item in assignments:
            profile=self.faculty.get(item.get('faculty_id')) if item.get('faculty_id') else None
            name=link(item['faculty_name'],profile['profile_url']) if profile else escape(item['faculty_name'])
            lines.append(f"{escape(item['role'])} (team-supplied): {name}")
        lines.append('The current offering and teaching assignment have not been independently verified.')
        return '\n'.join(lines)

    def topics(self, course):
        return [(section,syllabus) for sid in course['syllabus_ids']
                if (syllabus:=self.syllabi.get(sid)) for section in syllabus['sections']]

    def topic_resource_status(self, course_code, topic_number):
        """Return audited index candidate counts for a course's one-based syllabus topic."""
        course=self.topic_resources.get(course_code)
        if not course or not 1<=topic_number<=len(course.get('topics',[])):
            return None
        resources=course['topics'][topic_number-1].get('resources',{})
        chapters=len(resources.get('book_chapters',[]))
        lectures=len(resources.get('lectures',[]))
        if not chapters and not lectures:
            return 'no collected chapter or lecture match'
        labels=[]
        if chapters: labels.append(f'{chapters} chapter '+('candidate' if chapters==1 else 'candidates'))
        if lectures: labels.append(f'{lectures} lecture '+('candidate' if lectures==1 else 'candidates'))
        return ' · '.join(labels)

    def course_book_hits(self, course_code, limit=3):
        """Build source-grounded hits for books recommended in the linked syllabus."""
        result=[]; seen=set()
        for item in self.book_references:
            if course_code not in item.get('curriculum_codes',[]): continue
            key=re.sub(r'\W+','',item['bibliographic_text'].casefold())
            if key in seen: continue
            seen.add(key)
            result.append({'chunk_id':item['resource_id'],'text':item['bibliographic_text'],
                'metadata':{'entity_id':item['resource_id'],'document_type':'book_reference',
                    'curriculum_codes':item['curriculum_codes'],'source_syllabus_code':item['source_code'],
                    'evidence':item['evidence']}})
            if len(result)>=limit: break
        return result

    def course_book_reference_count(self, course_code):
        return len({re.sub(r'\W+','',item['bibliographic_text'].casefold())
                    for item in self.book_references if course_code in item.get('curriculum_codes',[])})

    def year_overview(self, year, topics=False, academic_year=DEFAULT_ACADEMIC_YEAR):
        courses=self.year_courses(year)
        title='Electives & additional options' if year=='options' else f'Year {year} · ECE, IIT Roorkee'
        lines=[f'<b>{title}</b>','Courses from the supplied curriculum.',academic_note(academic_year)]
        semesters=[None] if year=='options' else [int(year)*2-1,int(year)*2]
        for semester in semesters:
            lines += ['',f'<b>Semester {semester}</b>' if semester else '<b>No semester assigned in the source</b>']
            for c in courses:
                if semester is not None and semester not in self.semesters(c): continue
                categories = c.get('workbook_categories',[])
                category = categories[0].replace('_',' ') if year=='options' and categories else None
                suffix = f' · {escape(category)}' if category else ''
                lines.append(f"{escape(c['code'])} — {escape(c['title'])}{suffix}")
                if topics:
                    units=self.topics(c)
                    highlights=[s['text'].split(':',1)[0][:160] + ('…' if len(s['text'].split(':',1)[0])>160 else '') for s,_ in units[:3]]
                    lines.append('  Highlights: '+escape('; '.join(highlights)) if units else '  Detailed syllabus not collected yet.')
        sourced_entry=next((entry for course in courses for entry in course['curriculum_entries']
                            if entry.get('evidence',{}).get('page')),None)
        has_workbook_courses=any(course.get('workbook_records') for course in courses)
        if sourced_entry:
            page=sourced_entry['evidence']['page']
            lines += ['',link('View supplied curriculum',f'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_str_24.pdf#page={page}')]
        if has_workbook_courses:
            lines += ['', 'Source: ECE_Course_Structure.xlsx (user-supplied; applicability not verified).']
        if topics: lines.append('Topic highlights use related syllabus content; original syllabus codes are shown when you choose a course.')
        lines += ['', 'Which course would you like to study? Reply with its code or name.']
        return '\n'.join(lines)

    def render_course_hits(self, hits):
        """Render sourced course matches from curriculum and workbook chunks."""
        entries=[]; seen=set()
        for hit in hits:
            meta=hit.get('metadata',{})
            codes=([meta['course_code']] if meta.get('course_code') else meta.get('curriculum_codes',[]))
            for code in codes:
                course=self.course(str(code))
                if not course or course['code'] in seen: continue
                seen.add(course['code'])
                details=[f"<b>{escape(course['code'])} · {escape(course['title'])}</b>"]
                years=sorted({entry['year'] for entry in course['curriculum_entries'] if entry.get('year')})
                semesters=self.semesters(course)
                if years:
                    details.append('Year '+', '.join(map(str,years))+' · semester '+', '.join(map(str,semesters)))
                categories=course.get('workbook_categories',[])
                if categories:
                    details.append('Workbook categories: '+escape(', '.join(x.replace('_',' ') for x in categories)))
                entries.append('\n'.join(details))
                if len(entries)>=6: break
            if len(entries)>=6: break
        if not entries:
            return 'No sufficiently close course match was found in the supplied curriculum and course workbook. Try a more specific topic or browse /courses.'
        return ('<b>Related courses from the supplied curriculum and workbook</b>\n\n'
                +'\n\n'.join(entries)
                +'\n\nThe workbook does not state its effective cohort. These matches do not confirm current elective availability or enrollment.')

    def render_hits(self, hits, faculty=False):
        entries = []; seen = set(); counts = {'book':0,'lecture':0,'faculty':0}
        for hit in hits:
            entity = hit['metadata']['entity_id']
            if entity in seen: continue
            seen.add(entity)
            if faculty and entity in self.faculty and counts['faculty']<3:
                f = self.faculty[entity]; counts['faculty']+=1
                interests = f.get('research_interests_directory','')[:450]
                collected=next((s['evidence'].get('retrieved_at','')[:10] for s in f['sections'] if s.get('evidence',{}).get('retrieved_at')),'')
                entries.append(link(f['name'],f['profile_url'])+'\nResearch interests: '+escape(interests)+
                               ('\nSource collected: '+collected if collected else ''))
            elif not faculty and entity in self.books and counts['book']<2:
                b,c = self.books[entity]; counts['book']+=1
                entries.append('<b>Read</b> · '+link(f"Chapter {c['number']}: {c['title']}",c['url'])+
                    '\n'+escape(f"{b['title']} · {b['edition']}"))
            elif not faculty and entity in self.book_references_by_id and counts['book']<2:
                item=self.book_references_by_id[entity]; counts['book']+=1
                page=next((e.get('page') for e in item.get('evidence',[]) if e.get('page')),None)
                source_link=link('Syllabus reading list · '+item['source_code'],
                                 SYLLABUS_PDF+(f'#page={page}' if page else ''))
                entries.append('<b>Suggested book</b> · '+escape(item['bibliographic_text'])+'\n'+source_link+
                    '\n<i>Chapter contents for this edition were not collected.</i>')
            elif not faculty and entity in self.lectures and counts['lecture']<2:
                c,l = self.lectures[entity]; counts['lecture']+=1
                entries.append('<b>Watch</b> · '+link(l['title'],l['url'])+'\n'+escape(c['title'])+' · '+link('NPTEL outline',c['url']))
        if not entries:
            return 'I couldn’t find a sufficiently close match in the collected sources. Try a more specific ECE topic, change your course filter with /clear, or browse /courses.'
        intro = 'These research profiles may connect with your topic:' if faculty else 'Here are a few places to start studying:'
        note = ('Research interests do not confirm supervision availability.' if faculty else
                'These recommendations use collected syllabus references, chapter contents and lecture outlines, not full textbook answers. Check the linked edition and coverage.')
        return intro+'\n\n'+'\n\n'.join(entries)+'\n\n'+note+'\n<i>BGE-M3 semantic + keyword retrieval</i>'

    def visible_hits(self, hits, *, faculty=False, projects=False):
        """Use the same entities/quotas for generated context and visible citations."""
        result=[]; seen=set(); counts={'book':0,'lecture':0,'faculty':0,'project':0}
        for hit in hits:
            entity=hit.get('metadata',{}).get('entity_id')
            if entity in seen: continue
            kind=('project' if projects and entity in self.projects else
                  'faculty' if faculty and entity in self.faculty else
                  'book' if not faculty and not projects and (entity in self.books or entity in self.book_references_by_id) else
                  'lecture' if not faculty and not projects and entity in self.lectures else None)
            if kind is None or counts[kind]>=(3 if kind in ('project','faculty') else 2): continue
            seen.add(entity); counts[kind]+=1; result.append(hit)
        return result

    def render_projects(self, hits):
        entries=[]; seen=set()
        for hit in hits:
            project=self.projects.get(hit['metadata']['entity_id'])
            if not project or project['project_id'] in seen: continue
            seen.add(project['project_id'])
            fields=project['fields']; evidence=project['evidence']
            title=next((v for k,v in fields.items() if 'title' in k.lower()),None)
            if not title: continue
            details=[link(title,evidence.get('url',''))]
            for key,value in fields.items():
                if value and ('faculty' in key.lower() or 'year' in key.lower()):
                    details.append(escape(f'{key}: {value}'))
            if evidence.get('retrieved_at'):
                details.append('Source collected: '+escape(evidence['retrieved_at'][:10]))
            entries.append('\n'.join(details))
            if len(entries)==3: break
        if not entries:
            return 'No sufficiently close departmental project was found in the collected records. Try a specific research topic, such as VLSI or wireless communication.'
        return '<b>Related departmental project records</b>\n\n'+'\n\n'.join(entries)+ \
            '\n\nThese are recorded projects, not confirmed current openings or internship offers. Source collection dates do not confirm present availability.'
