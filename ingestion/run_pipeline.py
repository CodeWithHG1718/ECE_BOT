"""Run the reproducible source -> chunks -> BGE index -> topic-resource-map pipeline."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ingestion import bge_embeddings
from ingestion.build_topic_resource_map import build as build_topic_resource_map

OUT=ROOT/'datafiles/academic'


def load(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def verify_pipeline(index_path=None):
    """Fail closed if a collected source class is missing from chunks, index, or map."""
    chunks=read_jsonl(OUT/'embedding_chunks.jsonl')
    texts=read_jsonl(OUT/'embedding_texts.jsonl')
    counts=Counter(row['metadata']['document_type'] for row in chunks)
    syllabus=load('syllabus_courses.json')
    book_contents=load('book_contents.json')
    references=load('book_references.json')
    lectures=load('nptel_references.json')
    structure=load('course_structure.json')
    workbook=load('workbook_course_records.json')
    timetable=load('timetable_records.json')
    faculty_assignments=load('course_faculty_records.json')
    people=load('faculty_profiles.json')
    projects=load('department_projects.json')
    research=load('department_research.json')
    catalogue=load('course_catalogue.json')

    expected={}
    def expect(kind,identifiers):
        expected.setdefault(kind,set()).update(identifiers)
    expect('curriculum_entry',(row['entry_id'] for row in structure['entries']))
    expect('workbook_course',(row['record_id'] for row in workbook))
    expect('course_faculty_assignment',(row['record_id'] for row in faculty_assignments))
    expect('curriculum_rule',(f"page-{row['page']}" for row in structure['curriculum_rules']))
    expect('syllabus_objective',(row['syllabus_id'] for row in syllabus if row.get('objectives')))
    expect('syllabus_topic',(f"{row['syllabus_id']}:section:{position}"
        for row in syllabus for position,_ in enumerate(row.get('sections',[]),1)))
    expect('book_reference',(row['resource_id'] for row in references))
    expect('book_chapter',(chapter['chapter_id'] for book in book_contents for chapter in book['chapters']
        if chapter['review_status']!='source_label_requires_review'))
    expect('faculty_expertise',(row['faculty_id'] for row in people))
    expect('faculty_project',(f"{person['faculty_id']}:project:{position}"
        for person in people for position,_ in enumerate(person.get('profile_projects',[]))))
    allowed_sections={'research interests','projects','collaborations','publications','patents','research'}
    for person in people:
        for position,section in enumerate(person['sections']):
            heading=section['heading'].lower()
            if heading not in allowed_sections or (heading=='projects' and section['tables']):
                continue
            if not section.get('text','').strip():
                continue
            kind='faculty_'+heading.replace(' ','_')
            expect(kind,[f"{person['faculty_id']}:section:{position}"])
    expect('department_project',(row['project_id'] for row in projects))
    expect('research_group',(str(index) for index,row in enumerate(research)
        if any(s in row['url'] for s in ['Research%20Groups','Network%20','Microwave%20Group',
            'Microelectronics','Terahertz','Smart%20Electronic','C-DoT'])))
    expect('timetable_record',(row['record_id'] for row in timetable))
    expect('nptel_lecture',(f"{item['resource_id']}:{lesson['unit_id']}:{lesson['lesson_id']}"
        for item in lectures for lesson in item['lessons']))
    actual={kind:set() for kind in counts}
    for row in chunks:
        actual[row['metadata']['document_type']].add(row['metadata']['entity_id'])
    missing={kind:sorted(identifiers-actual.get(kind,set())) for kind,identifiers in expected.items()
             if identifiers-actual.get(kind,set())}
    unexpected=sorted(set(counts)-set(expected))
    if missing or unexpected:
        raise RuntimeError('Source-to-chunk entity coverage failed: '+json.dumps(
            {'missing_entities':missing,'unexpected_types':unexpected}))
    if len({row['chunk_id'] for row in chunks})!=len(chunks):
        raise RuntimeError('Duplicate embedding chunk IDs found.')
    if [(row['chunk_id'],row['text']) for row in chunks]!=[(row['id'],row['input']) for row in texts]:
        raise RuntimeError('Embedding text inputs do not match source chunk IDs and text.')
    if any(not row['metadata'].get('evidence') for row in chunks):
        raise RuntimeError('A chunk is missing source evidence.')

    chunk_hash=hashlib.sha256((OUT/'embedding_chunks.jsonl').read_bytes()).hexdigest()
    index_path=index_path or bge_embeddings.INDEX
    db_uri=index_path.resolve().as_uri()+'?mode=ro'
    with sqlite3.connect(db_uri,uri=True) as db:
        raw=db.execute('SELECT value FROM manifest WHERE id=1').fetchone()
        indexed_ids={row[0] for row in db.execute('SELECT id FROM documents')}
    manifest=json.loads(raw[0]) if raw else {}
    chunk_ids={row['chunk_id'] for row in chunks}
    if manifest.get('source_sha256')!=chunk_hash or indexed_ids!=chunk_ids:
        raise RuntimeError('Embedding index is stale or does not contain every current embedding chunk.')

    topic_map=load('topic_resource_map.json')
    map_manifest=topic_map['manifest']
    if (map_manifest.get('chunk_source_sha256')!=chunk_hash
            or map_manifest.get('embedding')!=manifest.get('embedding')
            or map_manifest.get('chunk_count')!=manifest.get('chunk_count')):
        raise RuntimeError('Topic-resource map is stale; rebuild the map after embedding.')
    course_rows=topic_map['courses']
    if {row['curriculum_code'] for row in course_rows}!={row['code'] for row in catalogue}:
        raise RuntimeError('Topic-resource map does not account for every course catalogue identity.')
    expected_pairs={}
    syllabus_by_id={row['syllabus_id']:row for row in syllabus}
    for course in catalogue:
        ids=[]
        for syllabus_id in course.get('syllabus_ids',[]):
            for position,_ in enumerate(syllabus_by_id[syllabus_id].get('sections',[]),1):
                ids.append(f'{syllabus_id}:section:{position}')
        expected_pairs[course['code']]=ids
    indexed_type={row['chunk_id']:row['metadata']['document_type'] for row in chunks}
    mapped_syllabus_ids={sid for row in catalogue for sid in row.get('syllabus_ids',[])}
    expected_unmapped={f"{row['syllabus_id']}:section:{position}"
        for row in syllabus if row['syllabus_id'] not in mapped_syllabus_ids
        for position,_ in enumerate(row.get('sections',[]),1)}
    actual_unmapped={row['topic_id'] for row in topic_map.get('unmapped_syllabus_topics',[])}
    expected_source_topics={f"{row['syllabus_id']}:section:{position}"
        for row in syllabus for position,_ in enumerate(row.get('sections',[]),1)}
    actual_source_topics={topic['topic_id'] for course in course_rows for topic in course['topics']}|actual_unmapped
    if actual_unmapped!=expected_unmapped or actual_source_topics!=expected_source_topics:
        raise RuntimeError('Resource map does not cover every mapped and unmapped source-syllabus topic.')
    if map_manifest.get('source_syllabus_topic_count')!=len(expected_source_topics):
        raise RuntimeError('Resource map source-topic count differs from the syllabus corpus.')
    for course in course_rows:
        actual=[row['topic_id'] for row in course['topics']]
        if actual!=expected_pairs[course['curriculum_code']]:
            raise RuntimeError(f"Topic map coverage/order mismatch for {course['curriculum_code']}.")
        for topic in course['topics']:
            for kind,expected_kind in (('book_chapters','book_chapter'),('lectures','nptel_lecture')):
                for item in topic['resources'][kind]:
                    if indexed_type.get(item['chunk_id'])!=expected_kind:
                        raise RuntimeError(f"Invalid {kind} candidate {item['chunk_id']} for {course['curriculum_code']}.")
                    if not item.get('url') or not item.get('evidence'):
                        raise RuntimeError(f"Resource candidate lacks URL/evidence: {item['entity_id']}.")
    for topic in topic_map.get('unmapped_syllabus_topics',[]):
        for kind,expected_kind in (('book_chapters','book_chapter'),('lectures','nptel_lecture')):
            for item in topic['resources'][kind]:
                if indexed_type.get(item['chunk_id'])!=expected_kind:
                    raise RuntimeError(f"Invalid unmapped-syllabus {kind} candidate {item['chunk_id']}.")
                if not item.get('url') or not item.get('evidence'):
                    raise RuntimeError(f"Unmapped-syllabus candidate lacks URL/evidence: {item['entity_id']}.")

    return {'courses':len(catalogue),'courses_with_syllabus':sum(bool(row['topics']) for row in course_rows),
        'courses_without_detailed_syllabus':sum(not row['topics'] for row in course_rows),
        'syllabus_topic_course_pairs':sum(len(row['topics']) for row in course_rows),
        'all_source_syllabus_topics':map_manifest.get('source_syllabus_topic_count'),
        'unmapped_legacy_syllabus_topics':len(topic_map.get('unmapped_syllabus_topics',[])),
        'embedding_chunks':len(chunks),'embedding_chunk_types':dict(sorted(counts.items())),
        'indexed_documents':len(indexed_ids),'resource_map_summary':topic_map['summary'],
        'embedding_provider':manifest['embedding']['provider'],'embedding_model':manifest['embedding']['model']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=('huggingface','ollama','azure'))
    parser.add_argument('--batch-size',type=int)
    parser.add_argument('--download',action='store_true',help='Allow Hugging Face to download BGE-M3 if it is not cached')
    parser.add_argument('--reextract-resources',action='store_true',
        help='Re-parse saved publisher and NPTEL snapshots before rebuilding')
    parser.add_argument('--reextract',action='store_true',
        help='Refresh saved curriculum/faculty extractions and resource snapshots before rebuilding')
    args=parser.parse_args()
    bge_embeddings.load_environment()
    embedder=bge_embeddings.configured_embedder(args.provider,args.download)
    index_path=bge_embeddings.index_for_provider(embedder.identity()['provider'])

    catalogue_command=[sys.executable,str(ROOT/'ingestion/build_catalogue.py')]
    if args.reextract: catalogue_command.append('--reextract')
    elif args.reextract_resources: catalogue_command.append('--reextract-resources')
    print('Stage 1/4 · Normalize source records and build evidence-backed chunks',flush=True)
    subprocess.run(catalogue_command,cwd=ROOT,check=True)

    print('Stage 2/4 · Embed every eligible chunk with a resumable provider-specific cache',flush=True)
    bge_embeddings.build(index=index_path,batch_size=args.batch_size,embedder=embedder)

    print('Stage 3/4 · Map every available syllabus topic to chapter and lecture candidates',flush=True)
    retriever=bge_embeddings.Retriever(embedder=embedder)
    build_topic_resource_map(retriever)

    print('Stage 4/4 · Check source coverage, model/index alignment, links, and topic coverage',flush=True)
    summary=verify_pipeline(index_path)
    print(json.dumps({'pipeline':'complete','integrity':'passed',**summary},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
