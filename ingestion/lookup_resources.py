"""Free local retrieval preview for testing course/topic resource guidance."""
import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'datafiles/academic'

STOP=set('a an the to of in for and or is are i my me we do does what where should can study learn about please how'.split())
def tokens(text): return [t for t in re.findall(r'[a-z0-9]+',text.lower()) if t not in STOP]
def search(query,course=None,limit=3):
    data=[json.loads(line) for line in (OUT/'embedding_chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    data=[r for r in data if r['metadata']['document_type'] in ('book_chapter','nptel_lecture') and (not course or course in r['metadata'].get('curriculum_codes',[]))]
    terms=set(tokens(query)); docs=[Counter(tokens(r['text'])) for r in data]
    frequencies=Counter(t for doc in docs for t in doc)
    groups={'books':[],'lectures':[]}
    for r,doc in zip(data,docs):
        matches=terms & doc.keys()
        if not matches:continue
        score=sum((1+math.log(doc[t]))*math.log(1+len(data)/(1+frequencies[t])) for t in matches)
        score*=len(matches)/max(1,len(terms))
        m=r['metadata']; group='books' if m['document_type']=='book_chapter' else 'lectures'
        groups[group].append({'score':round(score,4),'text':r['text'],'matched_terms':sorted(matches),
            'source_url':m.get('resource_url') or m.get('course_url'),'lecture_url':m.get('lecture_url'),
            'chapter':m.get('chapter_number'),'edition':m.get('edition'),'entity_id':m['entity_id'],
            'evidence':m['evidence']})
    for key in groups:
        candidates=sorted(groups[key],key=lambda r:-r['score']); unique={}
        for row in candidates: unique.setdefault(row['entity_id'],row)
        groups[key]=list(unique.values())[:limit]
    return {'query':query,'course':course,'method':'lexical_preview_not_embedding_similarity',
            'status':'matches_found' if any(groups.values()) else 'no_relevant_resource_found',**groups}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('query');p.add_argument('--course');p.add_argument('--limit',type=int,default=3)
    args=p.parse_args();print(json.dumps(search(args.query,args.course,args.limit),ensure_ascii=False,indent=2))
