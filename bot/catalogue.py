"""Telegram-independent source rendering; no LLM or Telegram API needed."""
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from bot.prompts import academic_note, DEFAULT_ACADEMIC_YEAR

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'datafiles/academic'


def link(label, url):
    if not isinstance(url, str) or urlparse(url).scheme not in ('https', 'http'):
        return escape(label)
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


class Catalogue:
    def __init__(self):
        self.courses = json.loads((DATA/'course_catalogue.json').read_text(encoding='utf-8'))
        self.syllabi = {s['syllabus_id']:s for s in json.loads((DATA/'syllabus_courses.json').read_text(encoding='utf-8'))}
        self.faculty = {f['faculty_id']:f for f in json.loads((DATA/'faculty_profiles.json').read_text(encoding='utf-8'))}
        self.projects = {p['project_id']:p for p in json.loads((DATA/'department_projects.json').read_text(encoding='utf-8'))}
        self.books = {}
        for book in json.loads((DATA/'book_contents.json').read_text(encoding='utf-8')):
            for chapter in book['chapters']:
                if chapter.get('review_status') != 'source_label_requires_review':
                    self.books[chapter['chapter_id']] = (book, chapter)
        self.lectures = {}
        for course in json.loads((DATA/'nptel_references.json').read_text(encoding='utf-8')):
            for lesson in course['lessons']:
                self.lectures[f"{course['resource_id']}:{lesson['unit_id']}:{lesson['lesson_id']}"] = (course, lesson)

    def semesters(self, course):
        return sorted({e['semester'] for e in course['curriculum_entries'] if e.get('semester')})

    def year_courses(self, year):
        if str(year) not in ('1','2','3','4','options'):
            raise ValueError('Choose year 1, 2, 3, 4 or options')
        return [c for c in self.courses if (not self.semesters(c) if year=='options' else
            any((s+1)//2==int(year) for s in self.semesters(c)))]

    def course(self, code):
        normalized = re.sub(r'[^A-Z0-9]', '', code.upper())
        return next((c for c in self.courses if re.sub(r'[^A-Z0-9]', '', c['code'].upper())==normalized),None)

    def course_details(self, course, academic_year=DEFAULT_ACADEMIC_YEAR):
        semesters = self.semesters(course)
        credits = ' / '.join(dict.fromkeys(e['credits_raw'] for e in course['curriculum_entries']))
        page = course['curriculum_entries'][0]['evidence']['page']
        url = 'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_str_24.pdf'
        return f"<b>{escape(course['code'])} · {escape(course['title'])}</b>\n" + \
            f"Semester: {', '.join(map(str,semesters)) if semesters else 'not assigned (elective / option)'}\n" + \
            f"Credits: {escape(credits)}\n" + link(f'Curriculum · page {page}', f'{url}#page={page}') + \
            '\n'+academic_note(academic_year) + \
            '\n\nUse this course as a filter, then send a study topic.'

    def topics(self, course):
        return [(section,syllabus) for sid in course['syllabus_ids']
                if (syllabus:=self.syllabi.get(sid)) for section in syllabus['sections']]

    def year_overview(self, year, topics=False, academic_year=DEFAULT_ACADEMIC_YEAR):
        courses=self.year_courses(year)
        title='Electives & additional options' if year=='options' else f'Year {year} · ECE, IIT Roorkee'
        lines=[f'<b>{title}</b>','Courses from the supplied curriculum.',academic_note(academic_year)]
        semesters=[None] if year=='options' else [int(year)*2-1,int(year)*2]
        for semester in semesters:
            lines += ['',f'<b>Semester {semester}</b>' if semester else '<b>No semester assigned in the source</b>']
            for c in courses:
                if semester is not None and semester not in self.semesters(c): continue
                lines.append(f"{escape(c['code'])} — {escape(c['title'])}")
                if topics:
                    units=self.topics(c)
                    highlights=[s['text'].split(':',1)[0][:160] + ('…' if len(s['text'].split(':',1)[0])>160 else '') for s,_ in units[:3]]
                    lines.append('  Highlights: '+escape('; '.join(highlights)) if units else '  Detailed syllabus not collected yet.')
        page=courses[0]['curriculum_entries'][0]['evidence']['page'] if courses else 1
        lines += ['',link('View supplied curriculum',f'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_str_24.pdf#page={page}')]
        if topics: lines.append('Topic highlights use related syllabus content; original syllabus codes are shown when you choose a course.')
        lines += ['', 'Which course would you like to study? Reply with its code or name.']
        return '\n'.join(lines)

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
            elif not faculty and entity in self.lectures and counts['lecture']<2:
                c,l = self.lectures[entity]; counts['lecture']+=1
                entries.append('<b>Watch</b> · '+link(l['title'],l['url'])+'\n'+escape(c['title'])+' · '+link('NPTEL outline',c['url']))
        if not entries:
            return 'I couldn’t find a sufficiently close match in the collected sources. Try a more specific ECE topic, change your course filter with /clear, or browse /courses.'
        intro = 'These research profiles may connect with your topic:' if faculty else 'Here are a few places to start studying:'
        note = 'Research interests do not confirm supervision availability.' if faculty else 'These recommendations use chapter contents and lecture outlines, not full textbook answers. Check the linked edition and coverage.'
        return intro+'\n\n'+'\n\n'.join(entries)+'\n\n'+note+'\n<i>BGE-M3 semantic + keyword retrieval</i>'

    def visible_hits(self, hits, *, faculty=False, projects=False):
        """Use the same entities/quotas for generated context and visible citations."""
        result=[]; seen=set(); counts={'book':0,'lecture':0,'faculty':0,'project':0}
        for hit in hits:
            entity=hit.get('metadata',{}).get('entity_id')
            if entity in seen: continue
            kind=('project' if projects and entity in self.projects else
                  'faculty' if faculty and entity in self.faculty else
                  'book' if not faculty and not projects and entity in self.books else
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
