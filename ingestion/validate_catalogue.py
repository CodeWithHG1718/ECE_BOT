"""Validate extraction coverage and citation integrity; not academic approval."""
import hashlib
import json
import re
from pathlib import Path
from extract_academic import ROOT, OUT, clean, save
from lxml import html
from lookup_resources import search

def load(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def norm(value): return re.sub(r'\W+','',value.lower())
def validate():
    checks=[]
    def check(name,condition,detail=None):
        checks.append({'check':name,'passed':bool(condition),'detail':detail})
    manifest=load('local_source_manifest.json')+load('web_source_manifest.json')
    source_ids={m['sha256'] for m in manifest}
    bad=[]
    for m in manifest:
        file=ROOT/m.get('snapshot',m.get('path',''))
        if hashlib.sha256(file.read_bytes()).hexdigest()!=m['sha256']: bad.append(str(file))
    check('Every recorded source hash matches its saved bytes',not bad,bad)
    for local in load('local_source_manifest.json'):
        remote=[m for m in manifest if m.get('url','').endswith(Path(local['path']).name)]
        check('Local PDF matches current official linked download: '+local['path'],any(m['sha256']==local['sha256'] for m in remote))
    structure=load('course_structure.json'); courses=load('syllabus_courses.json'); faculty=load('faculty_profiles.json')
    check('All 122 source curriculum rows, including elective options and minor/honours lists',len(structure['entries'])==122)
    check('Eight semester tables have total rows',len(structure['semester_totals'])==8)
    credit_review=[]
    for semester in range(1,9):
        entries=[e for e in structure['entries'] if e['semester']==semester]
        core=[e for e in entries if not e['code'].startswith('MSC/DHC')]
        def limits(rows):
            numbers=[list(map(int,re.findall(r'\d+',r['credits_raw']))) for r in rows]
            return [sum(min(n) for n in numbers),sum(max(n) for n in numbers)]
        core_range=limits(core); full_range=limits(entries)
        total=structure['semester_totals'][semester-1]
        printed=total['raw_cells'][4]
        expected=set(core_range+full_range)
        printed_numbers=set(map(int,re.findall(r'\d+',printed)))
        credit_review.append({'semester':semester,'main_curriculum_range':core_range,
            'including_optional_minor_honours_range':full_range,'printed_total':printed,
            'reconciled':expected==printed_numbers})
    check('Semester credit totals reconcile with optional minor/honours alternatives',all(r['reconciled'] for r in credit_review),credit_review)
    save('credit_totals_review.json',credit_review)
    check('Curriculum continuation titles retained',any(e['code']=='ECL-561' and e['title'].endswith('Devices') for e in structure['entries']) and any(e['code']=='ECL-526' and e['title'].endswith('Simulation') for e in structure['entries']))
    pages=load('btech_ec_syll_22.pdf.pages.json')
    covered={1,2,73,74}|{p for c in courses for p in c['pages']}
    check('Every syllabus page accounted for (index, course content, duplicate scan)',covered==set(range(1,80)),sorted(set(range(1,80))-covered))
    check('39 distinct full course blocks including three scanned appendices',len(courses)==39 and len({c['syllabus_id'] for c in courses})==39)
    missing=[]; cell_count=0
    for c in courses:
        output=norm(' '.join(s['text'] for s in c['sections']+c['resources']))
        for pn in c['pages']:
            if pn>=73: continue
            p=pages[pn-1]
            for ti,t in enumerate(p['tables'],1):
                if p.get('content_top_y') and t['bbox'][3]<p['content_top_y']:continue
                for ri,row in enumerate(t['rows'],1):
                    if len(row)<2:continue
                    body=' '.join(x or '' for x in (row[1:-1] if len(row)>2 else row[1:])); value=norm(body)
                    if len(value)<20 or re.search(r'Name of|Title/Authors|Contents|Practice\s+Classes of Two',body,re.I):continue
                    cell_count+=1
                    if value not in output:missing.append({'code':c['source_code'],'page':pn,'table':ti,'row':ri,'text':body})
    check('Every substantive PDF table body retained in topic/book records',not missing,{'cells_checked':cell_count,'missing':missing})
    check('All labs retain their experimental topics',all(c['sections'] for c in courses if c['source_code'] in ['ECN-252','ECN-351','ECN-352','ECN-354']))
    mapping={m['curriculum_code']:m for m in load('course_content_mappings.json')['mappings']}
    check('Signals uses ECN-203 under ECC-106; electromagnetics uses ECN-232/331 under ECC-203',mapping['ECC-106']['syllabus_codes']==['ECN-203'] and mapping['ECC-203']['syllabus_codes']==['ECN-232','ECN-331'])
    roster=next(m for m in manifest if m.get('url','').endswith('/FACULTY%20MEMBERS.html'))
    doc=html.fromstring((ROOT/roster['snapshot']).read_bytes().decode('utf-8'))
    roster_count=len(doc.xpath('//div[contains(@class,"faculty-card")]'))
    check('Every faculty directory card has an extracted profile',len(faculty)==roster_count==38 and all(f['sections'] and f['profile_extraction_status']=='extracted' for f in faculty))
    check('Every faculty member has sourced research interests',all(f['research_interests_directory'] and f['evidence'] for f in faculty))
    by_url={m.get('url'):m for m in manifest if m.get('url')}
    omitted=[]; source_headings=0
    for f in faculty:
        profile=html.fromstring((ROOT/by_url[f['profile_url']]['snapshot']).read_bytes().decode('utf-8'))
        retained=clean(' '.join(s['heading']+' '+s['text'] for s in f['sections'])+' '+
                       ' '.join(h['text'] for h in f.get('profile_header',[])))
        for column in profile.xpath('//div[@class="second"]'):
            for child in column:
                value=clean(child.text_content())
                if 'title-bar' in child.get('class','') or 'section-heading' in child.get('class',''):
                    source_headings+=1
                if value and value not in retained:
                    omitted.append({'faculty_id':f['faculty_id'],'locator':profile.getroottree().getpath(child)})
    check('Every faculty profile content block and heading retained',not omitted and source_headings==sum(len(f['sections']) for f in faculty),
          {'source_headings':source_headings,'omitted_blocks':omitted})
    chunks=[json.loads(line) for line in (OUT/'embedding_chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    check('Embedding IDs are unique',len(chunks)==len({c['chunk_id'] for c in chunks}))
    check('Every embedding has source evidence resolving to saved sources',all(c['text'].strip() and c['metadata']['evidence'] and set(c['metadata']['source_version_ids'])<=source_ids for c in chunks))
    texts=[json.loads(line) for line in (OUT/'embedding_texts.jsonl').read_text(encoding='utf-8').splitlines()]
    check('API input text and metadata stay in exact ID alignment',[(c['chunk_id'],c['text']) for c in chunks]==[(t['id'],t['input']) for t in texts])
    nptel=load('nptel_references.json')
    check('Twelve selected official NPTEL outlines and all 693 lesson references',len(nptel)==12 and sum(len(c['lessons']) for c in nptel)==693)
    check('NPTEL lessons retain course citations and concrete video URLs',all(l['url'] and l['title'] for c in nptel for l in c['lessons']))
    contents=load('book_contents.json')
    check('Eight selected publisher contents pages yield 100 chapter references',len(contents)==8 and sum(len(b['chapters']) for b in contents)==100)
    by_hash={m['sha256']:m for m in manifest}
    mismatches=[]
    for b in contents:
        doc=html.fromstring((ROOT/by_hash[b['source_version_id']]['snapshot']).read_bytes().decode('utf-8'))
        for chapter in b['chapters']:
            nodes=doc.xpath(chapter['locator'])
            if len(nodes)!=1 or clean(nodes[0].text_content())!=chapter['source_text']:mismatches.append(chapter['chapter_id'])
    check('Every chapter citation resolves to the exact saved publisher contents element',not mismatches,mismatches)
    check('Ambiguous publisher chapter label is excluded from embeddings',not any(c['metadata']['entity_id']=='razavi-fundamentals-2:chapter:17' for c in chunks))
    previews=[]
    for query,code,expected,lecture in [
        ('convolution','ECC-106','oppenheim-signals-2:chapter:2','nptel-108104100:3:14'),
        ('Boolean algebra','ECC-104','mano-digital-6:chapter:2',None),
        ('combinational logic','ECC-104','mano-digital-6:chapter:4','nptel-117106086:1:3'),
        ('waveguides','ECC-303','pozar-microwave-3:chapter:3','nptel-108103141:2:5')]:
        preview=search(query,code); previews.append(preview)
        check('Study lookup finds sourced chapter: '+query,any(b['entity_id']==expected for b in preview['books']))
        if lecture:
            check('Study lookup finds sourced lecture: '+query,any(l['entity_id']==lecture for l in preview['lectures']))
        else:
            check('Missing Boolean algebra title match remains explicit',not preview['lectures'])
    check('Unknown topic abstains',search('zzunmatchedtopiczz','ECC-106')['status']=='no_relevant_resource_found')
    check('Wrong course filter does not leak unrelated chapters',not search('waveguides','ECC-104')['books'])
    save('study_lookup_examples.json',previews)
    report={'validation_type':'extraction_integrity_and_coverage','all_passed':all(c['passed'] for c in checks),'checks':checks,
        'not_certified':['cohort applicability','official cross-code equivalence','current project availability','human approval for publication'],
        'known_gaps':['Unmatched curriculum courses have no detailed syllabus in the supplied file.',
          'Book contents cover eight selected books, not all 194 bibliography entries. Alternate editions are explicitly labelled.',
          'NPTEL collection covers twelve selected courses; coverage of every curriculum entry is listed in resource_coverage.json.',
          'The site homepage advertises 40/41 faculty while its linked directory lists 38. Coverage here is the linked directory.',
          'Public profiles can omit projects or contain outdated entries; absent information is not inferred.']}
    save('validation_report.json',report)
    print(json.dumps({'passed':report['all_passed'],'checks':len(checks),'failed':[c for c in checks if not c['passed']]},indent=2))
    if not report['all_passed']:raise SystemExit(1)
if __name__=='__main__':validate()
