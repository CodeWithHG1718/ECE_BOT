"""Offline extraction from checksummed official HTML snapshots."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote
from lxml import html
from fetch_sources import ROOT, CACHE

OUT = ROOT/'datafiles/academic'
def clean(value):
    return re.sub(r'\s+', ' ', value or '').strip()
def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def document(meta):
    return html.fromstring((ROOT/meta['snapshot']).read_bytes().decode('utf-8'))
def evidence(meta, locator, quote):
    return {'source_version_id':meta['sha256'], 'url':meta['url'],
            'retrieved_at':meta['retrieved_at'],'locator':locator,'quote':quote}
def tables(element):
    return [[[clean(c.text_content()) for c in row.xpath('./th|./td')]
             for row in table.xpath('.//tr')] for table in element.xpath('.//table')]
def extract():
    sources = [json.loads(f.read_text(encoding='utf-8')) for f in CACHE.glob('*.json')]
    by_url = {s['url']:s for s in sources}
    roster = next(s for s in sources if s['url'].endswith('/FACULTY%20MEMBERS.html'))
    doc = document(roster)
    cards = doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," faculty-card ")]')
    faculty = []
    for i, card in enumerate(cards,1):
        def field(cls):
            return clean(' '.join(e.text_content() for e in card.xpath('.//div[@class="'+cls+'"]')))
        url = quote(unquote(card.xpath('.//a[contains(.,"READ MORE")]/@href')[0]), safe=':/?=&%+#')
        f = {'faculty_id':'iitr-ece-'+url.rsplit('/',1)[-1].split('.')[0],
             'name':field('name'), 'designation':field('designation'),
             'profile_url':url, 'research_interests_directory':field('ui description'),
             'official_contact_fields':[clean(e.text_content()) for e in card.xpath('.//div[@class="info-content"]') if clean(e.text_content())],
             'sections':[], 'profile_header':[], 'profile_projects':[], 'review_status':'extracted',
             'supervision_availability':'not_stated',
             'evidence':[evidence(roster,f'faculty-card[{i}]',clean(card.text_content()))]}
        meta = by_url.get(url)
        if meta:
            page = document(meta)
            # Every profile content section is in the right-hand column. Navigation repeats headings.
            columns = page.xpath('//div[@class="second"]')
            for column in columns:
                current = None
                for child in column:
                    cls = child.get('class','')
                    is_heading = 'title-bar' in cls or 'section-heading' in cls
                    if is_heading:
                        if current:
                            f['sections'].append(current)
                        heading_node = child.xpath('.//*[@id]')
                        locator = '#'+heading_node[0].get('id') if heading_node else ('#'+child.get('id') if child.get('id') else page.getroottree().getpath(child))
                        current = {'heading':clean(child.text_content()),'locator':locator,
                                   'text':'','tables':[], 'links':[], 'evidence':evidence(meta,locator,'')}
                    elif current:
                        text = clean(child.text_content())
                        if text:
                            current['text'] += ('\n' if current['text'] else '')+text
                        current['tables'].extend(tables(child))
                        current['links'].extend({'label':clean(a.text_content()),'url':a.get('href')} for a in child.xpath('.//a[@href]'))
                    else:
                        text = clean(child.text_content())
                        links = [{'label':clean(a.text_content()),'url':a.get('href')}
                                 for a in child.xpath('descendant-or-self::a[@href]')]
                        if text or links:
                            locator = page.getroottree().getpath(child)
                            f['profile_header'].append({'text':text,'links':links,
                                'evidence':evidence(meta,locator,text)})
                if current:
                    f['sections'].append(current)
            for section in f['sections']:
                section['evidence']['quote']=section['text']
                if section['heading'].lower()=='projects':
                    for t in section['tables']:
                        if len(t)<2: continue
                        for rownum,row in enumerate(t[1:],2):
                            f['profile_projects'].append({'fields':dict(zip(t[0],row)), 'raw_cells':row,
                                'evidence':evidence(meta,section['locator']+f'/row[{rownum}]',' | '.join(row))})
            f['profile_extraction_status']='extracted' if f['sections'] else 'needs_parser_review'
            f['projects_status']='listed' if f['profile_projects'] else 'not_listed_in_parsed_tables'
        else:
            f['profile_extraction_status']='download_missing'
        faculty.append(f)
    save('faculty_profiles.json',faculty)
    project_source = next(s for s in sources if s['url'].endswith('/List%20of%20Sponsored%20Projects.html'))
    projects = []
    for ti,t in enumerate(tables(document(project_source)),1):
        if not t: continue
        for ri,row in enumerate(t[1:],2):
            projects.append({'project_id':'dept-project-'+hashlib.sha256('|'.join(row).encode()).hexdigest()[:16],
                             'fields':dict(zip(t[0],row)), 'raw_cells':row,
                             'evidence':evidence(project_source,f'table[{ti}]/row[{ri}]',' | '.join(row)),
                             'status_as_of_today':'not_inferred_from_year'})
    save('department_projects.json',projects)
    groups=[]
    for meta in sources:
        if '/Research/' not in meta['url']: continue
        page=document(meta)
        # Preserve useful departmental body containers without the repeated menus/footer.
        body=page.xpath('//div[contains(@class,"full-width-container")]')
        segments=[]
        for element in body:
            if any('full-width-container' in a.get('class','') for a in element.iterancestors()): continue
            value=clean(element.text_content())
            if value: segments.append(value)
        groups.append({'url':meta['url'],'sections':segments,'tables':tables(page),
                       'evidence':evidence(meta,'department body','\n'.join(segments))})
    save('department_research.json',groups)
    save('web_source_manifest.json',sources)
    print('Faculty:',len(faculty),'sections:',sum(len(f['sections']) for f in faculty),
          'profile projects:',sum(len(f['profile_projects']) for f in faculty),'department projects:',len(projects))
    print('Profiles needing parser review:',[f['name'] for f in faculty if f['profile_extraction_status']!='extracted'])

if __name__=='__main__': extract()
