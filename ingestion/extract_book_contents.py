"""Extract chapter names from public publisher contents pages, never full books."""
import json
import re
from urllib.parse import urljoin
from lxml import html
from extract_academic import ROOT, OUT, clean, save
from fetch_sources import CACHE

def normalize(value): return re.sub(r'\W+','',value.lower())

def extract():
    configs=json.loads((ROOT/'ingestion/book_contents_sources.json').read_text(encoding='utf-8'))
    references=json.loads((OUT/'book_references.json').read_text(encoding='utf-8'))
    books=[]
    for cfg in configs:
        meta=json.loads((CACHE/(cfg['source_id']+'.json')).read_text(encoding='utf-8'))
        doc=html.fromstring((ROOT/meta['snapshot']).read_bytes().decode('utf-8'))
        chapters=[]
        if cfg['parser']=='wiley_chapter_links':
            for a in doc.xpath('//a[@href]'):
                label=clean(a.text_content()); match=re.match(r'^Chapter\s+(\d+):\s*(.+)$',label)
                if not match: continue
                chapters.append({'number':int(match[1]),'title':match[2],
                    'url':urljoin(meta['final_url'],a.get('href')),'locator':doc.getroottree().getpath(a),'source_text':label})
        else:
            panels=doc.xpath('//*[@id="table-of-contents-tab" or @id="tableOfContents-tab"]')
            if not panels: raise ValueError('No publisher contents panel: '+cfg['book_id'])
            panel=panels[0]
            nodes=panel.xpath('.//h3|.//li|.//p')
            for node in nodes:
                if node.xpath('.//li|.//p'): continue
                label=clean(node.text_content())
                match=re.match(r'^(?:Chapter\s+)?(\d+)(?:\.(?!\d)|\s)\s*(.+)$',label)
                # HTML ordered lists may encode numbers in the list marker instead of the text.
                if not match and node.tag=='li' and node.getparent().tag=='ol':
                    number=list(node.getparent()).index(node)+int(node.getparent().get('start','1'))
                    title=label
                elif match:
                    number=int(match[1]); title=match[2]
                else:
                    # Keep numbered subsections or the list following a numbered chapter heading.
                    if chapters and (re.match(r'^\d+\.\d+\s',label) or (node.tag=='li' and node.getparent().tag=='ul')):
                        chapters[-1].setdefault('subtopics',[]).append({'title':label,'locator':doc.getroottree().getpath(node)})
                    continue
                if number>30: continue
                chapters.append({'number':number,'title':title.rstrip('.'),
                    'url':meta['url']+'#'+panel.get('id'),'locator':doc.getroottree().getpath(node),'source_text':label})
        dedup={}
        for chapter in chapters: dedup.setdefault(chapter['number'],chapter)
        chapters=list(dedup.values())
        if not chapters: raise ValueError('Empty chapter extraction: '+cfg['book_id'])
        matches=[]
        for r in references:
            if all(normalize(term) in normalize(r['bibliographic_text']) for term in cfg['reference_terms']):
                matches.append(r['resource_id'])
        for chapter in chapters:
            chapter['chapter_id']=cfg['book_id']+':chapter:'+str(chapter['number'])
            chapter['evidence']={'source_version_id':meta['sha256'],'url':meta['url'],
                 'retrieved_at':meta['retrieved_at'],'locator':chapter['locator'],'quote':chapter['source_text']}
            chapter['page_number']=None  # No page number is inferred from a chapter number.
            chapter['review_status']='source_label_requires_review' if cfg['book_id']=='razavi-fundamentals-2' and chapter['number']==17 else 'extracted_from_publisher'
        books.append({k:v for k,v in cfg.items() if k not in ('parser','reference_terms')} | {
            'source_url':meta['url'],'source_version_id':meta['sha256'],'chapters':chapters,
            'related_syllabus_reference_ids':matches,'relationship':'related_title_not_automatic_edition_equivalence',
            'coverage':'chapters_listed_on_public_publisher_page','full_text_ingested':False})
    save('book_contents.json',books)
    print('Publisher contents:',len(books),'books;',sum(len(b['chapters']) for b in books),'chapter references',flush=True)
    return books

if __name__=='__main__': extract()
