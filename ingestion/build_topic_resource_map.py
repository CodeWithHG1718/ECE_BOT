"""Build a source-backed resource candidate map for every collected course topic."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot.catalogue import topic_query
from ingestion.bge_embeddings import Retriever, configured_embedder, unpacked

OUT=ROOT/'datafiles/academic'
SYLLABUS_PDF=('https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/'
              'static/Courses%20Offered/B.Tech/btech_ec_syll_22.pdf')


def load(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def source_url(evidence):
    page=next((item.get('page') for item in evidence if item.get('page')),None)
    return SYLLABUS_PDF+(f'#page={page}' if page else '')


def candidate(hit, expected_type):
    metadata=hit['metadata']
    if metadata.get('document_type')!=expected_type:
        raise ValueError(f"Expected {expected_type}, got {metadata.get('document_type')}")
    if expected_type=='book_chapter':
        url=metadata.get('resource_url')
        label=hit['text'].splitlines()[0]
        detail={'chapter_number':metadata.get('chapter_number'),
                'edition':metadata.get('edition')}
    else:
        url=metadata.get('lecture_url') or metadata.get('course_url')
        label=hit['text'].splitlines()[0]
        detail={'course_url':metadata.get('course_url')}
    return {'entity_id':metadata['entity_id'],'chunk_id':hit['chunk_id'],
            'label':label[:300],'text':hit['text'][:1000],'url':url,
            'curriculum_codes':metadata.get('curriculum_codes',[]),
            **detail,'scores':hit.get('scores',{}),'evidence':metadata.get('evidence',[])}


def reading_reference(item):
    return {'resource_id':item['resource_id'],'bibliographic_text':item['bibliographic_text'],
            'source_syllabus_code':item['source_code'],'source_url':source_url(item.get('evidence',[])),
            'evidence':item.get('evidence',[]),
            'chapter_mapping_status':item.get('chapter_mapping_status')}


def build(retriever):
    catalogue=load('course_catalogue.json')
    syllabi={item['syllabus_id']:item for item in load('syllabus_courses.json')}
    references=load('book_references.json')
    chunk_path=OUT/'embedding_chunks.jsonl'
    chunk_bytes=chunk_path.read_bytes()
    chunk_hash=hashlib.sha256(chunk_bytes).hexdigest()
    if retriever.manifest.get('source_sha256')!=chunk_hash:
        raise RuntimeError('The BGE index does not match embedding_chunks.jsonl; rebuild embeddings first.')

    # Pre-embed unique topic queries in batches so this exhaustive audit does not
    # issue one model call per course/topic pair.
    tasks=[]; unmapped_tasks=[]; queries=[]; seen_queries=set();mapped_syllabus_ids=set()
    for course in catalogue:
        number=0
        for syllabus_id in course.get('syllabus_ids',[]):
            mapped_syllabus_ids.add(syllabus_id)
            syllabus=syllabi[syllabus_id]
            for section_index,section in enumerate(syllabus.get('sections',[]),1):
                number+=1
                query=topic_query(section['text'])
                tasks.append((course,syllabus,section_index,number,section,query))
                if query and query not in seen_queries:
                    seen_queries.add(query);queries.append(query)
    for syllabus in syllabi.values():
        if syllabus['syllabus_id'] in mapped_syllabus_ids: continue
        for section_index,section in enumerate(syllabus.get('sections',[]),1):
            query=topic_query(section['text'])
            unmapped_tasks.append((syllabus,section_index,section,query))
            if query and query not in seen_queries:
                seen_queries.add(query);queries.append(query)
    missing=[query for query in queries if query not in retriever.query_cache]
    for start in range(0,len(missing),32):
        batch=missing[start:start+32]
        for query,vector in zip(batch,retriever.embedder.encode(batch)):
            retriever.query_cache[query]=unpacked(vector,retriever.dimensions)
        print(f'Prepared topic query vectors {min(start+len(batch),len(missing))}/{len(missing)}',flush=True)

    references_by_code={};references_by_source={}
    for item in references:
        references_by_source.setdefault(item['source_code'],[]).append(reading_reference(item))
        for code in item.get('curriculum_codes',[]):
            references_by_code.setdefault(code,[]).append(reading_reference(item))

    courses_out=[];unmapped_out=[]
    pairs_with_candidate=0; no_topic_matches=0; total_chapters=0; total_lectures=0
    for course in catalogue:
        code=course['code']; rows=[]; related_syllabus_codes=[]
        for task_course,syllabus,section_index,number,section,query in tasks:
            if task_course['code']!=code: continue
            if syllabus['source_code'] not in related_syllabus_codes:
                related_syllabus_codes.append(syllabus['source_code'])
            books=[candidate(hit,'book_chapter') for hit in retriever.search(
                query,code,['book_chapter'],3)] if query else []
            lectures=[candidate(hit,'nptel_lecture') for hit in retriever.search(
                query,code,['nptel_lecture'],3)] if query else []
            if books or lectures: pairs_with_candidate+=1
            else: no_topic_matches+=1
            total_chapters+=len(books);total_lectures+=len(lectures)
            rows.append({'topic_number':number,
                'topic_id':f"{syllabus['syllabus_id']}:section:{section_index}",
                'source_syllabus_code':syllabus['source_code'],'syllabus_id':syllabus['syllabus_id'],
                'topic_text':section['text'],'query':query,'evidence':section.get('evidence',[]),
                'resources':{'book_chapters':books,'lectures':lectures},
                'status':'candidate_resources_found' if books or lectures else 'no_collected_topic_resource_match'})
        codes=[row['source_syllabus_code'] for row in rows]
        course_refs=references_by_code.get(code,[])
        syllabus_available=bool(course.get('syllabus_ids'))
        courses_out.append({'curriculum_code':code,'title':course['title'],
            'syllabus_status':'detailed_syllabus_available' if syllabus_available else 'detailed_syllabus_not_collected',
            'source_syllabus_codes':list(dict.fromkeys(codes)),
            'course_reading_list':course_refs,'topics':rows,
            'coverage':{'topic_count':len(rows),
                'topics_with_candidate_resources':sum(r['status']=='candidate_resources_found' for r in rows),
                'topics_without_collected_match':sum(r['status']=='no_collected_topic_resource_match' for r in rows),
                'syllabus_book_recommendations':len(course_refs),
                'book_chapter_candidates':sum(len(r['resources']['book_chapters']) for r in rows),
                'lecture_candidates':sum(len(r['resources']['lectures']) for r in rows)}})
    for syllabus,section_index,section,query in unmapped_tasks:
        books=[candidate(hit,'book_chapter') for hit in retriever.search(
            query,None,['book_chapter'],3)] if query else []
        lectures=[candidate(hit,'nptel_lecture') for hit in retriever.search(
            query,None,['nptel_lecture'],3)] if query else []
        if books or lectures: pairs_with_candidate+=1
        else: no_topic_matches+=1
        total_chapters+=len(books);total_lectures+=len(lectures)
        unmapped_out.append({'source_syllabus_code':syllabus['source_code'],'title':syllabus['title'],
            'syllabus_id':syllabus['syllabus_id'],'source_status':'not_mapped_to_primary_curriculum',
            'topic_number':section_index,'topic_id':f"{syllabus['syllabus_id']}:section:{section_index}",
            'topic_text':section['text'],'query':query,'evidence':section.get('evidence',[]),
            'course_reading_list':references_by_source.get(syllabus['source_code'],[]),
            'resources':{'book_chapters':books,'lectures':lectures},
            'status':'global_candidate_search_unverified' if books or lectures else 'no_collected_topic_resource_match'})
    course_codes={course['code'] for course in catalogue}
    if {course['curriculum_code'] for course in courses_out}!=course_codes:
        raise ValueError('Resource map must contain each catalogue course exactly once.')
    map_data={'manifest':{'format_version':1,'embedding':retriever.manifest['embedding'],
            'chunk_source_sha256':chunk_hash,'chunk_count':retriever.manifest['chunk_count'],
            'course_count':len(courses_out),'course_topic_pair_count':len(tasks),
            'source_syllabus_topic_count':sum(len(s.get('sections',[])) for s in syllabi.values()),
            'unmapped_source_syllabus_topic_count':len(unmapped_tasks),
            'unique_topic_query_count':len(queries),
            'retrieval_method':retriever.manifest['embedding']['model']+' dense + BM25 reciprocal-rank fusion; automatic candidates, not academic approval'},
        'summary':{'courses_with_detailed_syllabus':sum(bool(c['topics']) for c in courses_out),
            'courses_without_detailed_syllabus':sum(not c['topics'] for c in courses_out),
            'topics_with_candidate_resources':pairs_with_candidate,
            'topics_without_collected_match':no_topic_matches,
            'book_chapter_candidates':total_chapters,'lecture_candidates':total_lectures},
        'courses':courses_out,'unmapped_syllabus_topics':unmapped_out}
    out=OUT/'topic_resource_map.json'
    out.write_text(json.dumps(map_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'path':str(out),'summary':map_data['summary'],
                      'course_topic_pair_count':len(tasks)},ensure_ascii=False,indent=2),flush=True)
    return map_data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=('huggingface','ollama','azure'))
    parser.add_argument('--download',action='store_true',help='Allow initial Hugging Face model download')
    args=parser.parse_args()
    embedder=configured_embedder(args.provider,args.download)
    build(Retriever(embedder=embedder))


if __name__=='__main__':
    main()
