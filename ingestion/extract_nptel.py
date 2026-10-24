"""Read serialized public course outlines without executing webpage JavaScript."""
import json
import re
from lxml import html
from fetch_sources import ROOT, CACHE
from extract_academic import save

class LiteralParser:
    def __init__(self,text): self.text=text; self.i=0
    def ws(self):
        while self.i<len(self.text) and self.text[self.i].isspace(): self.i+=1
    def value(self):
        self.ws(); c=self.text[self.i]
        if c=='"':
            value,end=json.JSONDecoder().raw_decode(self.text[self.i:]); self.i+=end; return value
        if c in '{[':
            self.i+=1; result={} if c=='{' else []; closing='}' if c=='{' else ']'
            while True:
                self.ws()
                if self.text[self.i]==closing: self.i+=1; return result
                if c=='{':
                    if self.text[self.i]=='"': key=self.value()
                    else:
                        m=re.match(r'[A-Za-z_$][\w$]*',self.text[self.i:])
                        if not m: raise ValueError('Expected property name')
                        key=m[0]; self.i+=len(key)
                    self.ws()
                    if self.text[self.i]!=':': raise ValueError('Expected colon')
                    self.i+=1; result[key]=self.value()
                else: result.append(self.value())
                self.ws()
                if self.text[self.i]==',': self.i+=1
                elif self.text[self.i]!=closing: raise ValueError('Non-literal JavaScript is not supported')
        m=re.match(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|undefined',self.text[self.i:])
        if not m: raise ValueError('Non-literal value at offset '+str(self.i))
        self.i+=len(m[0]); return None if m[0]=='undefined' else json.loads(m[0])

MAPPINGS={
    '108104100':['ECC-106'],
    '108107142':['ECC-102','ECC-204','ECL-343'],
    '117106086':['ECC-104'],
    '108106151':['ECC-301','ECT-109'],
    '108107129':['ECL-573','ECT-111'],
    '108101037':['EEE-101'],
    '117101051':['ECC-202','ECL-515'],
    '108106172':['ECC-205'],
    '108105114':['ECC-203'],
    '108104130':['ECC-203'],
    '108103141':['ECC-303','ECC-302','ECT-101','ECT-102','ECT-103'],
    '117105143':['ECC-201','ECC-304']
}
def extract():
    records=[]
    for f in sorted(CACHE.glob('*.json')):
        meta=json.loads(f.read_text(encoding='utf-8'))
        if not meta['url'].startswith('https://nptel.ac.in/courses/'): continue
        course_id=meta['url'].rsplit('/',1)[-1]
        doc=html.fromstring((ROOT/meta['snapshot']).read_bytes().decode('utf-8'))
        scripts=doc.xpath('//script/text()')
        script=next((s for s in scripts if 'courseOutline:' in s),None)
        if script is None: raise ValueError('Missing NPTEL outline '+course_id)
        outline=LiteralParser(script.split('courseOutline:',1)[1]).value()
        lessons=[]
        for unit in outline.get('units',[]):
            for lesson in unit.get('lessons',[]):
                video=lesson.get('youtube_id')
                lessons.append({'unit_id':unit.get('id'),'unit_title':unit.get('name'),
                    'lesson_id':lesson.get('id'),'title':lesson.get('name'),
                    'concepts_covered':lesson.get('concepts_covered'),
                    'url':'https://www.youtube.com/watch?v='+video if video and re.fullmatch(r'[\w-]{11}',video) else None})
        records.append({'resource_id':'nptel-'+course_id,'resource_type':'nptel_course',
            'title':outline.get('title'),'instructor':outline.get('professor'),'institute':outline.get('instituteName'),
            'url':meta['url'],'curriculum_codes':MAPPINGS.get(course_id,[]),
            'mapping_type':'study_resource_topic_match_not_official_course_equivalence',
            'lessons':lessons,'evidence':{'source_version_id':meta['sha256'],'url':meta['url'],
            'retrieved_at':meta['retrieved_at'],'locator':'serialized courseOutline; units[].lessons[]'},
            'coverage':'starter_reference_collection','full_video_or_transcript_ingested':False})
    save('nptel_references.json',records)
    print('NPTEL courses',len(records),'lecture references',sum(len(r['lessons']) for r in records),flush=True)
    return records

if __name__=='__main__': extract()
