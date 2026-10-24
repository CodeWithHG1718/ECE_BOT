"""Extract curriculum and syllabus locally, retaining source-specific evidence."""
from pathlib import Path
import hashlib
import json
import re
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'datafiles/academic'
OUT.mkdir(parents=True,exist_ok=True)
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def normcode(s): return re.sub(r'\s+','',s or '').strip('.')
def stable(*parts): return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:24]
def source(path):
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'published_at':None}
def ev(src,page,locator,raw):
    return {'source_version_id':src['sha256'],'path':src['path'],'page':page,'locator':locator,'quote':raw}
def read_pdf(path):
    src=source(path)
    pages=[]
    with pdfplumber.open(path) as pdf:
        for n,p in enumerate(pdf.pages,1):
            tables=[{'bbox':list(t.bbox),'rows':t.extract()} for t in p.find_tables()]
            starts=p.search(r'10\.\s*Details',case=False)
            pages.append({'page':n,'text':p.extract_text() or '', 'tables':tables,
                          'content_top_y':starts[0]['top'] if starts else None,
                          'extraction_method':'pdfplumber','source_version_id':src['sha256']})
    return src,pages

def structure(src,pages):
    entries=[]; totals=[]; supplementary=[]
    for p in pages:
        n=p['page']; term=None; group=None
        if n<4:
            supplementary.append({'page':n,'text':p['text'],'tables':p['tables'],'evidence':ev(src,n,'whole page',p['text'])})
            continue
        for ti,table in enumerate(p['tables'],1):
            for ri,row in enumerate(table['rows'],1):
                raw=[clean(c) for c in row]
                if '(Autumn)' in raw: term='Autumn'; continue
                if '(Spring)' in raw: term='Spring'; continue
                if raw and re.search(r'TEB-[A-H]',raw[0]): group=raw[0]; continue
                if 'Total' in raw:
                    totals.append({'year':n-3 if n<8 else None,'term':term,'raw_cells':raw,'evidence':ev(src,n,f'table {ti} row {ri}',' | '.join(raw))}); continue
                if not raw or not re.fullmatch(r'\d+\.?',raw[0]):
                    if n==8 and not raw[0] and len(raw)>4 and raw[4] and entries:
                        entries[-1]['title']+=' '+raw[4]
                        entries[-1].setdefault('continuation_evidence',[]).append(ev(src,n,f'table {ti} row {ri}',' | '.join(raw)))
                    # Keep split Tinkering/Mentoring assessment subrows with the parent course.
                    if n==4 and len(raw)>5 and raw[5]=='M-2' and entries:
                        entries[-1]['component_rows'].append(raw)
                    continue
                if n==8:
                    fields=[raw[0],''.join(raw[1:4]),' '.join(x for x in raw[4:11] if x)]+raw[11:]
                elif n==4:
                    fields=raw[:5]+raw[6:]
                elif n in (6,7):
                    fields=raw[:9]+raw[10:]
                elif n==12 and len(raw)==10:
                    fields=[raw[0],''.join(raw[1:4]),' '.join(x for x in raw[4:8] if x)]+raw[8:]
                else: fields=raw
                code=normcode(fields[1]); title=clean(fields[2])
                kind='course'
                if n in (8,9): kind='program_elective_option'
                if n in (10,11): kind='talent_enhancement_option'
                if n==12: kind='minor_option' if ti==1 else 'honours_option'
                elif n<8 and not re.fullmatch(r'[A-Z]+-\d+',code): kind='elective_or_project_slot'
                credits=fields[4]
                e={'entry_id':stable(src['sha256'],n,ti,ri),'course_id':'curriculum-'+code,
                   'code':code,'title':title,'entry_type':kind,
                   'year':n-3 if n<8 else None,'semester':(n-4)*2+(1 if term=='Autumn' else 2) if n<8 else None,
                   'term':fields[3] if n==12 else term,'group':group,
                   'subject_area':fields[3] if n!=12 else None,'credits_raw':credits,
                   'contact_hours_raw':dict(zip(['L','T','P'],fields[5:8])) if n!=12 else {},
                   'examination_hours_raw':dict(zip(['theory','practical'],fields[8:10])) if n!=12 else {},
                   'assessment_raw':dict(zip(['CWS','PRS','MTE','ETE','PRE'],fields[10:15])) if n!=12 else {},
                   'component_rows':[raw] if n==4 and code=='TMI-101' else [],
                   'raw_cells':raw,'evidence':ev(src,n,f'table {ti} row {ri}',' | '.join(raw)),
                   'review_status':'extracted','applicability':'project_primary_curriculum_per_user'}
                entries.append(e)
    return {'source':src,'entries':entries,'semester_totals':totals,'curriculum_rules':supplementary}

HEADER=re.compile(r'(?:Subject|Course)\s*Code\s*:\s*(.*?)\s*Course\s*Title\s*:\s*(.*?)(?=\n\s*2\.)',re.I|re.S)
def syllabus(src,pages):
    courses=[]; current=None; mode='topics'
    for p in pages:
        if p['page']>=73: continue  # duplicate scans and manually transcribed appendices below
        text=p['text']; m=HEADER.search(text)
        if m:
            code=normcode(m[1]); title=clean(m[2])
            current={'syllabus_id':stable(src['sha256'],p['page']), 'source_code':code,'title':title,
                     'source_version_id':src['sha256'],'pages':[], 'sections':[], 'resources':[],
                     'header_raw':text[:text.lower().find('10.')], 'review_status':'extracted',
                     'source_applicability':'legacy_source_used_for_project_content_mapping', 'warnings':[]}
            def field(pattern):
                found=re.search(pattern,text,re.I|re.S)
                return clean(found[1]) if found else None
            current['objectives']=field(r'9\.\s*Objective\s*:\s*(.*?)(?=10\.)')
            current['prerequisites_raw']=field(r'Pre-requisite\s*:\s*(.*?)(?=\n\s*\d+\.)')
            current['credits_raw']=field(r'5\.\s*Credits\s*:\s*(.*?)(?=6\.)')
            current['contact_hours_raw']=field(r'2\.\s*Contact Hours\s*:\s*(.*?)(?=3\.)')
            current['evidence']=ev(src,p['page'],'course header',m[0])
            courses.append(current); mode='topics'
        if not current: continue
        current['pages'].append(p['page'])
        if not text:
            current['warnings'].append(f'Image-only page {p["page"]} requires visual transcription; not assumed part of this course.')
            continue
        for ti,tab in enumerate(p['tables'],1):
            if m and p.get('content_top_y') is not None and tab['bbox'][3]<p['content_top_y']: continue
            for ri,row in enumerate(tab['rows'],1):
                r=[clean(c) for c in row]
                joined=' | '.join(r)
                if re.search(r'Name of.*(?:Books|Authors)|Title/Authors|Year of Publication',joined,re.I): mode='books'; continue
                if re.search(r'Contents?.*Contact|Contact.*Hours',joined,re.I) and 'Name of' not in joined: mode='topics'; continue
                if len(r)<2: continue
                if len(r)>3: r=[r[0],clean(' '.join(r[1:-1])),r[-1]]
                number=r[0].strip('. ')
                if r[1].lower()=='total': continue
                if number.isdigit() or (mode=='topics' and (re.fullmatch(r'\d+(?: \d+)+',number) or (not number and not current['sections']))):
                    body=r[1]
                    if not body: continue
                    item={'ordinal':int(number) if number.isdigit() else len(current['sections'])+1,'ordinal_raw':number,'text':body,
                          'evidence':[ev(src,p['page'],f'table {ti} row {ri}',joined)],
                          'extraction_method':p['extraction_method']}
                    if mode=='books':
                        item['year_raw']=r[-1] if len(r)>2 else None
                        item['chapter_mapping_status']='table_of_contents_not_collected'
                        current['resources'].append(item)
                    else:
                        item['contact_hours_raw']=r[-1] if len(r)>2 else None
                        current['sections'].append(item)
                elif not number and r[1] and r[1].lower()!='total':
                    target=current['resources'] if mode=='books' else current['sections']
                    if target:
                        target[-1]['text']+=' '+r[1]
                        target[-1]['evidence'].append(ev(src,p['page'],f'table {ti} row {ri}',joined))
        current.setdefault('raw_pages',[]).append({'page':p['page'],'text':text})
    for course in courses:
        combined='\n'.join(p['text'] for p in course['raw_pages'])
        detail=re.split(r'10\.\s*Details of (?:the )?[Cc]ourse\s*:?|10\.\s*Details of the course\s*:?',combined,maxsplit=1)
        content=detail[-1] if len(detail)>1 else combined
        parts=re.split(r'(?:\d+\.\s*)?Suggested [Bb]ooks?\s*:',content,maxsplit=1)
        course['content_text']=parts[0].strip()
        if len(parts)>1: course['bibliography_text']=parts[1].strip()
        if course['source_code']=='ECN-316' and not course['resources']:
            text='Gonzalez & Woods, “Digital Image Processing”, 3rd Edn.'
            course['resources'].append({'ordinal':1,'text':text,'year_raw':None,
                'chapter_mapping_status':'table_of_contents_not_collected',
                'extraction_method':'pdfplumber_inline_bibliography',
                'evidence':[ev(src,72,'Suggested book',text)]})
    return courses

def main():
    manifest=[]
    for filename in ['btech_ec_str_24.pdf','btech_ec_syll_22.pdf']:
        src,pages=read_pdf(ROOT/'data'/filename); manifest.append(src)
        save(filename+'.pages.json',pages)
        if 'str_24' in filename: save('course_structure.json',structure(src,pages))
        else:
            courses=syllabus(src,pages)
            # The image duplicate on p73 preserves an SM Charts paragraph damaged in p68's text layer.
            embedded=next(c for c in courses if c['source_code']=='EC-343')
            embedded_section=next(s for s in embedded['sections'] if s['ordinal']==3)
            charts='SM Charts: State machine charts, Derivation of SM Charts, Realization of SM Chart, Implementation of Binary Multiplier, dice game controller, A/D and D/A conversion.'
            embedded_section['text']=re.sub(r'SM Ch.*$','',embedded_section['text']).rstrip()+' '+charts
            embedded_section['evidence'].append(ev(src,73,'Contents row 3, SM Charts (visual transcription)',charts))
            embedded['duplicate_source_pages']=[73,74]
            scans=json.loads((ROOT/'ingestion/scanned_syllabus_transcription.json').read_text(encoding='utf-8'))
            for item in scans['courses']:
                course={k:v for k,v in item.items() if k not in ('topics','books')}
                course.update(syllabus_id=stable(src['sha256'],item['pages'][0]),source_version_id=src['sha256'],
                    review_status='visually_transcribed',source_applicability='legacy_source_used_for_project_content_mapping',
                    warnings=[],sections=[],resources=[],raw_pages=[],evidence=ev(src,item['pages'][0],'course header',item['source_code']+' '+item['title']))
                for i,(body,hours) in enumerate(item['topics'],1):
                    course['sections'].append({'ordinal':i,'text':body,'contact_hours_raw':hours,
                        'extraction_method':scans['method'],'evidence':[ev(src,item['pages'][0],f'Contents row {i}',body)]})
                for i,(body,year) in enumerate(item['books'],1):
                    course['resources'].append({'ordinal':i,'text':body,'year_raw':year,
                        'extraction_method':scans['method'],'chapter_mapping_status':'table_of_contents_not_collected',
                        'evidence':[ev(src,item['pages'][-1],f'Suggested Books row {i}',body)]})
                course['content_text']='\n'.join(t[0] for t in item['topics'])
                course['bibliography_text']='\n'.join(b[0]+' ('+b[1]+')' for b in item['books'])
                courses.append(course)
            save('syllabus_courses.json',courses)
            save('syllabus_scan_audit.json',{'duplicate_pages':scans['duplicate_pages'],
                 'visually_transcribed_pages':[75,76,77,78,79],'source':src})
    save('local_source_manifest.json',manifest)
    print('Extracted source pages, curriculum rows and syllabus course blocks.',flush=True)
if __name__=='__main__': main()
