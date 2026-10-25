"""Build offline, model-independent embedding inputs. This never calls a paid API."""
import csv
import hashlib
import json
import re
import uuid
from pathlib import Path
from import_course_workbook import extract_records as extract_workbook_records, curriculum_entry, course_text
from import_timetable import extract_records as extract_timetable_records
from import_course_faculty import extract_records as extract_course_faculty_records

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'datafiles/academic'

def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def load(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def pieces(text,limit=1800):
    """Keep paragraph/sentence boundaries when practical; no text is discarded."""
    words=text.split(); current=[]; size=0
    for word in words:
        if current and size+len(word)+1>limit:
            yield ' '.join(current); current=[]; size=0
        current.append(word); size+=len(word)+1
    if current: yield ' '.join(current)

def merge_workbook_courses(catalogue, records):
    """Keep the PDF catalogue and workbook evidence together without aliasing codes."""
    by_code={course['code']:course for course in catalogue}
    for record in records:
        course=by_code.get(record['code'])
        if course is None:
            normalized=re.sub(r'[^A-Z0-9]+','-',record['code'].upper()).strip('-')
            course={'course_id':'curriculum-'+normalized,'code':record['code'],
                    'title':record['title'],'curriculum_entries':[],
                    'syllabus_ids':[],'syllabus_source_codes':[],
                    'content_mapping':None,'content_status':'not_in_supplied_syllabus',
                    'curriculum_is_primary':False}
            catalogue.append(course);by_code[record['code']]=course
        course.setdefault('workbook_records',[]).append(record)
        categories=course.setdefault('workbook_categories',[])
        if record['category'] not in categories: categories.append(record['category'])
        entry=curriculum_entry(record)
        if entry:
            existing=course.setdefault('curriculum_entries',[])
            same_slot=any(e.get('year')==entry['year'] and e.get('semester')==entry['semester']
                          and e.get('title')==entry['title'] for e in existing)
            if not same_slot: existing.append(entry)
    return catalogue

def build(refresh_resources=False):
    structure=load('course_structure.json'); syllabus=load('syllabus_courses.json'); people=load('faculty_profiles.json')
    workbook_courses=extract_workbook_records()
    timetable_records=extract_timetable_records()
    course_faculty_records=extract_course_faculty_records(people)
    save('workbook_course_records.json',workbook_courses)
    save('timetable_records.json',timetable_records)
    save('course_faculty_records.json',course_faculty_records)
    mapping=json.loads((ROOT/'ingestion/course_content_mappings.json').read_text(encoding='utf-8'))
    by_source={s['source_code']:s for s in syllabus}
    by_curriculum={e['code']:e for e in structure['entries']}
    links=mapping['mappings']; mapped={m['curriculum_code']:m for m in links}
    reverse={}
    for m in links:
        assert m['curriculum_code'] in by_curriculum,m
        m['syllabus_ids']=[]
        m['evidence']=[by_curriculum[m['curriculum_code']]['evidence']]
        for code in m['syllabus_codes']:
            assert code in by_source,m
            m['syllabus_ids'].append(by_source[code]['syllabus_id'])
            m['evidence'].append(by_source[code]['evidence'])
            reverse.setdefault(code,[]).append(m['curriculum_code'])
    save('course_content_mappings.json',mapping)
    catalogue=[]; reviews=[]
    for code,e in by_curriculum.items():
        occurrences=[x for x in structure['entries'] if x['code']==code]
        m=mapped.get(code)
        item={'course_id':e['course_id'],'code':code,'title':occurrences[0]['title'],
              'curriculum_entries':occurrences,'syllabus_ids':m['syllabus_ids'] if m else [],
              'syllabus_source_codes':m['syllabus_codes'] if m else [],
              'content_mapping':m,'content_status':('available_partial' if m['coverage']=='partial' else 'available') if m else 'not_in_supplied_syllabus',
              'curriculum_is_primary':True}
        catalogue.append(item)
        reviews.append({'curriculum_code':code,'title':item['title'],
                        'source_syllabus_codes':'; '.join(item['syllabus_source_codes']),
                        'content_status':item['content_status'],'coverage':m['coverage'] if m else '',
                        'reason':m['reason'] if m else 'No supported course-content match in supplied syllabus.'})
    catalogue=merge_workbook_courses(catalogue,workbook_courses)
    for assignment in course_faculty_records:
        course=next((item for item in catalogue if item['code']==assignment['course_code']),None)
        if course is None:
            raise ValueError(f"Course instructor refers to unknown course code: {assignment['course_code']}")
        course.setdefault('faculty_assignments',[]).append(assignment)
    save('course_catalogue.json',catalogue)
    with (OUT/'course_mapping_review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(reviews[0]));writer.writeheader();writer.writerows(reviews)

    books=[]
    for s in syllabus:
        for resource in s['resources']:
            text=resource['text']
            quoted=re.search(r'[“"]([^”"]+)[”"]',text)
            books.append({'resource_id':str(uuid.uuid5(uuid.NAMESPACE_URL,s['syllabus_id']+':book:'+str(resource['ordinal']))),
                          'resource_type':'syllabus_recommended_book', 'bibliographic_text':text,
                          'title_candidate':quoted[1] if quoted else None,'year_raw':resource['year_raw'],
                          'source_code':s['source_code'],'curriculum_codes':reverse.get(s['source_code'],[]),
                          'syllabus_id':s['syllabus_id'],'evidence':resource['evidence'],
                          'table_of_contents':None,'chapter_mapping_status':'next_phase_collect_edition_specific_toc',
                          'full_text_ingested':False})
    save('book_references.json',books)
    if refresh_resources:
        # Refresh after rebuilding reference IDs from the current syllabus.
        from extract_book_contents import extract as extract_book_contents
        book_contents=extract_book_contents()
    else:
        book_contents=load('book_contents.json')
    for book_reference in books:
        related=[b['book_id'] for b in book_contents if book_reference['resource_id'] in b['related_syllabus_reference_ids']]
        book_reference['related_contents_ids']=related
        if related: book_reference['chapter_mapping_status']='related_contents_available_verify_edition'
    save('book_references.json',books)

    chunks=[]
    def add(kind,entity_id,heading,text,evidence,**metadata):
        if not text or not text.strip(): return
        if isinstance(evidence,dict): evidence=[evidence]
        for part,body in enumerate(pieces(text),1):
            content=heading+'\n'+body
            key='ece-catalogue-v1:'+kind+':'+entity_id+':'+str(part)+':'+hashlib.sha256(content.encode()).hexdigest()
            chunks.append({'chunk_id':str(uuid.uuid5(uuid.NAMESPACE_URL,key)),'text':content,
                'metadata':{'institute_id':'iit-roorkee','department_id':'ece','document_type':kind,
                'entity_id':entity_id,'part':part,'source_version_ids':sorted({e['source_version_id'] for e in evidence}),
                'publication_status':'staging','embedding_model':None,'chunking_version':'v1-1800characters',
                'evidence':evidence,**metadata}})
    for e in structure['entries']:
        text=f"Curriculum course: {e['code']} — {e['title']}. Entry type: {e['entry_type']}. "
        if e['year']: text+=f"Year {e['year']}, semester {e['semester']} ({e['term']}). "
        if e['group']: text+=f"Group: {e['group']}. "
        text+=f"Credits as printed: {e['credits_raw']}. Contact hours as printed: {e['contact_hours_raw']}."
        add('curriculum_entry',e['entry_id'],e['code']+' '+e['title'],text,[e['evidence']]+e.get('continuation_evidence',[]),curriculum_codes=[e['code']],applicability='project_primary_curriculum')
    for record in workbook_courses:
        add('workbook_course',record['record_id'],record['code']+' '+record['title'],
            course_text(record),record['evidence'],curriculum_codes=[record['code']],
            course_code=record['code'],course_title=record['title'],
            course_category=record['category'],study_year=record['year'],
            semester=record['semester'],term=record['term'],source_sheet=record['evidence']['sheet'],
            applicability=record['applicability'])
    for assignment in course_faculty_records:
        course=next(item for item in catalogue if item['code']==assignment['course_code'])
        applicability=assignment['applicability']
        text=(f"Course {assignment['course_code']}: {course['title']}. "
              f"{assignment['role']} listed as {assignment['faculty_name']}. "
              f"This is {assignment['provided_by']} information; the current teaching assignment is unverified.")
        add('course_faculty_assignment',assignment['record_id'],
            assignment['course_code']+' professor '+assignment['faculty_name'],text,
            assignment['evidence'],curriculum_codes=[assignment['course_code']],
            course_code=assignment['course_code'],course_title=course['title'],
            faculty_name=assignment['faculty_name'],faculty_id=assignment['faculty_id'],
            role=assignment['role'],applicability=applicability)
    for rule in structure['curriculum_rules']:
        add('curriculum_rule',f"page-{rule['page']}",'ECE curriculum requirements',rule['text'],rule['evidence'],applicability='project_primary_curriculum')
    for s in syllabus:
        codes=reverse.get(s['source_code'],[])
        heading=', '.join(codes)+(' | ' if codes else '')+s['title']+' | source syllabus '+s['source_code']
        metadata={'curriculum_codes':codes,'source_syllabus_code':s['source_code'],'syllabus_id':s['syllabus_id'],
                  'applicability':'project_content_association' if codes else 'source_syllabus_only'}
        if s.get('objectives'): add('syllabus_objective',s['syllabus_id'],heading,s['objectives'],s['evidence'],**metadata)
        for i,section in enumerate(s['sections'],1):
            add('syllabus_topic',s['syllabus_id']+':section:'+str(i),heading,section['text'],section['evidence'],**metadata)
        # Preserve complete detail text as an independent audit/retrieval fallback for merged tables.
        # It lives in the canonical course file; avoid duplicate embedding of the same topics.
        s['curriculum_codes']=codes
    save('syllabus_courses.json',syllabus)
    for b in books:
        add('book_reference',b['resource_id'],b['source_code']+' recommended reading',b['bibliographic_text'],b['evidence'],curriculum_codes=b['curriculum_codes'],source_syllabus_code=b['source_code'],chapter_mapping_status=b['chapter_mapping_status'])
    for book in book_contents:
        for chapter in book['chapters']:
            if chapter['review_status']=='source_label_requires_review': continue
            topics='; '.join(t['title'] for t in chapter.get('subtopics',[]))
            text=f"Chapter {chapter['number']}: {chapter['title']}."
            if topics: text+=' Contents topics: '+topics
            text+=' Edition notes: '+' '.join(book['notes']) if book['notes'] else ''
            ev=[chapter['evidence']]
            ev.extend(dict(chapter['evidence'],locator=t['locator'],quote=t['title']) for t in chapter.get('subtopics',[]))
            add('book_chapter',chapter['chapter_id'],book['title']+' — '+book['authors']+' — '+book['edition'],text,ev,
                curriculum_codes=book['curriculum_codes'],book_id=book['book_id'],edition=book['edition'],
                chapter_number=chapter['number'],resource_url=chapter['url'],mapping_type='study_resource_topic_match')
    for f in people:
        add('faculty_expertise',f['faculty_id'],f['name']+' — '+f['designation'],f['research_interests_directory'],f['evidence'],faculty_id=f['faculty_id'],supervision_availability='not_stated')
        for i,section in enumerate(f['sections']):
            heading=section['heading'].lower()
            if heading not in ('research interests','projects','collaborations','publications','patents','research'): continue
            if heading=='projects' and section['tables']:
                for j,project in enumerate(f['profile_projects']):
                    add('faculty_project',f['faculty_id']+':project:'+str(j),f['name']+' — project',
                        '; '.join(k+': '+v for k,v in project['fields'].items() if v),project['evidence'],faculty_id=f['faculty_id'],current_status='not_inferred')
            else:
                add('faculty_'+heading.replace(' ','_'),f['faculty_id']+':section:'+str(i),f['name']+' — '+section['heading'],section['text'],section['evidence'],faculty_id=f['faculty_id'])
    for p in load('department_projects.json'):
        add('department_project',p['project_id'],'ECE department sponsored project','; '.join(k+': '+v for k,v in p['fields'].items() if v),p['evidence'],current_status='not_inferred')
    for i,r in enumerate(load('department_research.json')):
        if any(s in r['url'] for s in ['Research%20Groups','Network%20','Microwave%20Group','Microelectronics','Terahertz','Smart%20Electronic','C-DoT']):
            add('research_group',str(i),'ECE research group','\n'.join(r['sections']),r['evidence'])
    for record in timetable_records:
        code=str(record.get('course_code') or '')
        course=next((c for c in catalogue if c['code']==code),None)
        sections=', '.join(record['student_sections']) or 'student section not recorded'
        course_title=f" Course title: {course['title']}." if course else ''
        text=(f"Recurring ECE timetable entry for study year {record['study_year']}, "
              f"{record.get('academic_year') or 'academic year not stated'} {record.get('term') or 'term not stated'}, "
              f"{record.get('day') or 'day not stated'} {record.get('start_time') or 'time unknown'}–"
              f"{record.get('end_time') or 'time unknown'}. "
              f"{record.get('session_type') or 'Session type not stated'} for {code or 'course not identified'}."
              f"{course_title} "
              f"Timetable batch label: {record['course_batch'] or 'not stated'}. "
              f"Student sections: {sections}. "
              f"Room: {record.get('room') or 'not stated'}. Faculty: {record.get('faculty') or 'not stated'}. "
              "OCR-extracted recurring weekly data; cohort applicability and changes are unverified.")
        add('timetable_record',record['record_id'],
            f"Year {record['study_year']} timetable {code} {record.get('day') or ''}",text,
            record['evidence'],curriculum_codes=[code] if course else [],
            course_code=code or None,course_title=course['title'] if course else None,
            study_year=record['study_year'],academic_year=record['academic_year'],term=record['term'],
            day=record['day'],start_time=record['start_time'],end_time=record['end_time'],
            session_type=record['session_type'],course_batch=record['course_batch'],
            student_sections=record['student_sections'],room=record['room'],faculty=record['faculty'],
            applicability=record['applicability'])
    if refresh_resources:
        from extract_nptel import extract as extract_nptel
        nptel=extract_nptel()
    else:
        nptel=load('nptel_references.json')
    for r in nptel:
        for lesson in r['lessons']:
            text=f"{lesson['unit_title']}. {lesson['title']}."
            if lesson.get('concepts_covered'): text+=' '+lesson['concepts_covered']
            if lesson['url']: text+=' Watch: '+lesson['url']
            ev=dict(r['evidence'],locator=f"courseOutline.units[id={lesson['unit_id']}].lessons[id={lesson['lesson_id']}]",quote=lesson['title'])
            add('nptel_lecture',r['resource_id']+':'+str(lesson['unit_id'])+':'+str(lesson['lesson_id']),
                r['title']+' — '+r['instructor']+' ('+r['institute']+')',text,ev,
                curriculum_codes=r['curriculum_codes'],resource_institute=r['institute'],
                course_url=r['url'],lecture_url=lesson['url'],mapping_type=r['mapping_type'])
    coverage=[]
    for c in catalogue:
        code=c['code']
        related_books=[b['book_id'] for b in book_contents if code in b['curriculum_codes']]
        related_lectures=[r['resource_id'] for r in nptel if code in r['curriculum_codes']]
        coverage.append({'curriculum_code':code,'title':c['title'],
            'book_reference_count':sum(code in b['curriculum_codes'] for b in books),
            'books_with_contents':related_books,'nptel_courses':related_lectures,
            'resource_status':'linked_resources_available' if related_books or related_lectures else ('bibliography_only' if any(code in b['curriculum_codes'] for b in books) else 'resource_not_collected')})
    save('resource_coverage.json',coverage)
    assert len({c['chunk_id'] for c in chunks})==len(chunks)
    (OUT/'embedding_chunks.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks),encoding='utf-8')
    (OUT/'embedding_texts.jsonl').write_text(''.join(json.dumps({'id':c['chunk_id'],'input':c['text']},ensure_ascii=False)+'\n' for c in chunks),encoding='utf-8')
    stats={'curriculum_entries':len(structure['entries']),
           'workbook_curriculum_rows':sum(1 for r in workbook_courses if r['category']=='curriculum_course'),
           'merged_course_entries':sum(len(c['curriculum_entries']) for c in catalogue),
           'pdf_curriculum_entries':len(structure['entries']),'curriculum_codes':len(catalogue),
           'workbook_course_records':len(workbook_courses),
           'workbook_course_codes':len({r['code'] for r in workbook_courses}),
           'course_faculty_assignments':len(course_faculty_records),
           'timetable_records':len(timetable_records),'syllabus_course_blocks':len(syllabus),
           'curriculum_codes_with_content':len(links),'book_references':len(books),'faculty_profiles':len(people),
           'faculty_profile_projects':sum(len(f['profile_projects']) for f in people),
           'department_project_entries':len(load('department_projects.json')),'embedding_chunks':len(chunks),
           'nptel_courses':len(nptel),'nptel_lecture_references':sum(len(r['lessons']) for r in nptel),
           'books_with_contents':len(book_contents),'book_chapter_references':sum(len(b['chapters']) for b in book_contents),
           'embedding_characters':sum(len(c['text']) for c in chunks),'paid_api_calls':0}
    save('catalogue_statistics.json',stats)
    print(json.dumps(stats,indent=2),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Rebuild the local ECE catalogue and embedding inputs.')
    parser.add_argument('--reextract',action='store_true',
        help='Re-extract curriculum PDFs, faculty and cached book/NPTEL sources before rebuilding (requires ingestion dependencies).')
    parser.add_argument('--reextract-resources',action='store_true',
        help='Re-extract book contents and NPTEL outlines from saved HTML snapshots before rebuilding.')
    args=parser.parse_args()
    if args.reextract:
        from extract_academic import main as extract_pdfs
        from extract_faculty import extract as extract_people
        extract_pdfs(); extract_people()
    # Resource extraction runs from inside build, after current syllabus book
    # reference IDs have been regenerated.
    build(refresh_resources=args.reextract or args.reextract_resources)
