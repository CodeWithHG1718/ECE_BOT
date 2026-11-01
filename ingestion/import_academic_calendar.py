"""Import the supplied ETE draft schedule and Autumn academic calendar.

Only schedule/calendar pages are retained. The ETE PDF's student enrollment
rosters and examination conduct annexures are deliberately excluded.
"""
from datetime import datetime
import hashlib
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'datafiles/academic'
ETE_SOURCE = ROOT / 'data/Draft_Schedule_ETE_Autumn_2026-27.pdf'
ETE_SNAPSHOT = ROOT / 'data/ete_schedule_records_snapshot.json'
ETE_SNAPSHOT_CHECKSUM = ROOT / 'data/ete_schedule_records_snapshot.sha256'
CALENDAR_SOURCE = ROOT / 'data/Autumn_Calander_2026-27_All_Programme_other_than_MBA.pdf'

COURSE_CODE = re.compile(r'(?<![A-Z0-9])([A-Z]{2,5}-\d{3})(?![A-Z0-9])', re.I)
DATE_DMY = re.compile(r'(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)')
DATE_MONTH = re.compile(r'(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,\s*|\s+)(20\d{2})\b')
MONTHS = {name.casefold():number for number,name in enumerate(
    ('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
DATE_MONTH_RANGE = re.compile(
    r'(?i)\b(?P<start_month>January|February|March|April|May|June|July|August|September|October|November|December)\s+'
    r'(?P<start_day>\d{1,2})\s*[–—-]\s*(?:(?P<end_month>January|February|March|April|May|June|July|August|September|October|November|December)\s*)?'
    r'(?P<end_day>\d{1,2}),?\s*(?P<year>20\d{2})\b')
WEEKDAYS = ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
DAY_RE = re.compile(r'(?i)\b(?:'+'|'.join(WEEKDAYS)+r')\b')
EXAM_TIMES = {
    '09:00 AM - 12:15 PM': ('09:00', '12:15'),
    '02:30 PM - 05:45 PM': ('14:30', '17:45'),
}


def _clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _iso_dmy(value):
    return datetime.strptime(value, '%d.%m.%Y').date().isoformat()


def _month_date(value):
    match = DATE_MONTH.search(value or '')
    if not match:
        return None
    return datetime.strptime(' '.join(match.groups()), '%B %d %Y').date().isoformat()


def _evidence(source, source_hash, page, locator, quote):
    return {'source_version_id': source_hash,
            'path': source.relative_to(ROOT).as_posix(),
            'page': page, 'locator': locator, 'quote': _clean(quote)[:1200]}


def _stable_id(namespace, source_hash, page, position):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f'{namespace}:{source_hash}:page-{page}:row-{position}'))


def _extract_slots(pdf):
    """Read date/time/slot associations from the ETE Annexure-I table."""
    page = pdf.pages[3]
    slot_map = {}
    for table in page.extract_tables() or []:
        if not any(any('DATE' in str(c or '').upper() for c in row) for row in table):
            continue
        current_date = None
        for row in table:
            cells = [str(c or '').strip() for c in row]
            joined = ' '.join(cells)
            date_match = DATE_MONTH.search(joined)
            if date_match:
                current_date = datetime.strptime(' '.join(date_match.groups()), '%B %d %Y').date().isoformat()
            time_cell = next((c for c in cells if re.search(r'\b\d{1,2}\.\d{2}\s*(?:AM|PM)\s*-', c, re.I)), None)
            if not current_date or not time_cell:
                continue
            hour_match = re.search(r'(\d{1,2}\.\d{2})\s*(AM|PM)\s*-\s*(\d{1,2}\.\d{2})\s*(AM|PM)',time_cell,re.I)
            if not hour_match:
                continue
            def time_value(value, meridiem):
                hour,minute=map(int,value.split('.'))
                if meridiem.upper()=='PM' and hour!=12: hour+=12
                if meridiem.upper()=='AM' and hour==12: hour=0
                return f'{hour:02d}:{minute:02d}'
            start=time_value(hour_match.group(1),hour_match.group(2))
            end=time_value(hour_match.group(3),hour_match.group(4))
            slot = next((c for c in cells if c and c != time_cell
                         and re.fullmatch(r'[A-Z0-9]+(?:/[A-Z0-9]+)*',c)), None)
            slot_map.setdefault(current_date,{})[(start,end)] = slot
    if not slot_map:
        raise ValueError('Could not read ETE date/time/slot mappings from Annexure-I page 4.')
    return slot_map


def _cell_assignments(value):
    """Extract course codes and keep the adjacent program/range assignment text."""
    text = _clean(value)
    matches = list(COURSE_CODE.finditer(text))
    records = []
    for index, match in enumerate(matches):
        end = matches[index+1].start() if index+1 < len(matches) else len(text)
        allocation = text[match.end():end].strip(' \t,;|')
        records.append((match.group(1).upper(), allocation or None))
    return records


def load_ete_snapshot(snapshot_path=ETE_SNAPSHOT, source_pdf_path=ETE_SOURCE):
    """Load the public-safe schedule-only JSON snapshot and verify both hashes."""
    snapshot_path=Path(snapshot_path)
    checksum_path=Path(str(snapshot_path).removesuffix('.json')+'.sha256')
    if not snapshot_path.is_file() or not checksum_path.is_file():
        raise FileNotFoundError('Safe ETE schedule snapshot and its .sha256 checksum are required.')
    raw=snapshot_path.read_bytes()
    expected=checksum_path.read_text(encoding='ascii').split()[0].lower()
    actual=hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r'[0-9a-f]{64}',expected) or expected!=actual:
        raise ValueError('Safe ETE schedule snapshot checksum mismatch.')
    payload=json.loads(raw.decode('utf-8'))
    source=payload.get('source',{})
    source_hash=source.get('sha256','')
    if (payload.get('schema_version')!=1 or not re.fullmatch(r'[0-9a-f]{64}',source_hash)
            or source.get('path')!='data/Draft_Schedule_ETE_Autumn_2026-27.pdf'
            or source.get('included_pages')!=[5,30]):
        raise ValueError('Safe ETE snapshot source metadata is invalid.')
    records=payload.get('records')
    if not isinstance(records,list) or not records:
        raise ValueError('Safe ETE snapshot must contain schedule records.')
    for record in records:
        evidence=record.get('evidence',{})
        if (evidence.get('source_version_id')!=source_hash
                or evidence.get('path')!=source['path']
                or evidence.get('page') not in range(5,31)
                or record.get('source_status')!='draft_unreviewed'):
            raise ValueError('Safe ETE snapshot record has invalid source provenance.')
        content=' '.join(str(record.get(field) or '') for field in
            ('record_type','course_code','department_name','room','programme_allocation'))
        content+=' '+str(evidence.get('quote') or '')
        if re.search(r'\bEnrollment\s*No\b|\b\d{8}\b',content,re.I):
            raise ValueError('Safe ETE snapshot contains enrollment-roster information.')
    source_pdf_path=Path(source_pdf_path)
    if source_pdf_path.is_file() and hashlib.sha256(source_pdf_path.read_bytes()).hexdigest()!=source_hash:
        raise ValueError('Safe ETE snapshot does not match the local original PDF hash.')
    return payload


def write_ete_snapshot(records=None, path=ETE_SOURCE, snapshot_path=ETE_SNAPSHOT):
    """Write only parsed pages 5-30, retaining the original PDF hash and page evidence."""
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Original ETE PDF required to create the safe snapshot: {path}')
    records=records if records is not None else extract_ete_records(path)
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    if any(record['evidence']['source_version_id']!=source_hash for record in records):
        raise ValueError('ETE snapshot records do not match the original PDF source hash.')
    payload={'schema_version':1,
        'source':{'path':path.relative_to(ROOT).as_posix(),'sha256':source_hash,
                  'included_pages':[5,30],
                  'description':'Schedule and venue assignments only; enrollment roster pages are excluded.'},
        'records':records}
    snapshot_path=Path(snapshot_path)
    raw=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    snapshot_path.write_bytes(raw)
    checksum_path=Path(str(snapshot_path).removesuffix('.json')+'.sha256')
    checksum_path.write_text(hashlib.sha256(raw).hexdigest()+'  '+snapshot_path.name+'\n',encoding='ascii')
    return payload


def extract_ete_records(path=ETE_SOURCE, snapshot_path=ETE_SNAPSHOT):
    """Read Annexures I/II only; never import the enrollment-number pages."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError('Install ingestion/requirements.txt to parse the ETE PDF (pdfplumber is required).') from exc
    path=Path(path)
    if not path.is_file():
        return load_ete_snapshot(snapshot_path=snapshot_path,source_pdf_path=path)['records']
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    records=[]
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages)<30:
            raise ValueError('ETE schedule PDF is incomplete; expected Annexures I and II through page 30.')
        slot_map=_extract_slots(pdf)
        for page_number in range(5,31):
            page=pdf.pages[page_number-1]
            text=page.extract_text() or ''
            heading=re.search(r'\((November\s+\d{1,2},\s*2026),\s*([A-Za-z]+)\)',text,re.I)
            if not heading:
                raise ValueError(f'Could not read the exam date from ETE PDF page {page_number}.')
            exam_date=datetime.strptime(heading.group(1),'%B %d, %Y').date().isoformat()
            day=heading.group(2).capitalize()
            tables=page.extract_tables() or []
            table=max(tables,key=len,default=[])
            if not table:
                continue
            department_mode=False
            row_number=0
            for row in table:
                cells=[_clean(cell) for cell in row]
                joined=' '.join(cells)
                if any('Department Name' in cell for cell in cells):
                    department_mode=True
                    continue
                if any('Room No' in cell for cell in cells) or any('Timings' == cell for cell in cells):
                    continue
                if len(cells)<3:
                    continue
                first, morning, afternoon=cells[0],cells[1],cells[2]
                if not first:
                    continue
                row_number+=1
                if department_mode:
                    # These cells are department-hosted exam venue names, not course IDs.
                    for label,raw in (('09:00 AM - 12:15 PM',morning),('02:30 PM - 05:45 PM',afternoon)):
                        if not raw:
                            continue
                        start,end=EXAM_TIMES[label]
                        quote=f'{first} · {label} · {raw}'
                        records.append({
                            'record_id':_stable_id('ete-department-venue',source_hash,page_number,f'{row_number}-{label}'),
                            'record_type':'department_exam_venue','course_code':None,
                            'department_name':first,'exam_date':exam_date,'day':day,
                            'start_time':start,'end_time':end,
                            'slot':slot_map.get(exam_date,{}).get((start,end)),
                            'room':raw,'programme_allocation':None,
                            'academic_session':'Autumn 2026-27','exam_type':'End Term Examination',
                            'source_status':'draft_unreviewed','applicability':'all_programmes_source_assignment_not_student_specific',
                            'evidence':_evidence(path,source_hash,page_number,f'Annexure-II department venue row {row_number}',quote)})
                    continue
                for label,raw in (('09:00 AM - 12:15 PM',morning),('02:30 PM - 05:45 PM',afternoon)):
                    start,end=EXAM_TIMES[label]
                    for course_code,allocation in _cell_assignments(raw):
                        quote=f'{first} · {label} · {course_code} {allocation or ""}'
                        records.append({
                            'record_id':_stable_id('ete-course-exam',source_hash,page_number,
                                                   f'{row_number}-{label}-{course_code}-{allocation or ""}'),
                            'record_type':'course_exam','course_code':course_code,
                            'department_name':None,'exam_date':exam_date,'day':day,
                            'start_time':start,'end_time':end,
                            'slot':slot_map.get(exam_date,{}).get((start,end)),
                            'room':first,'programme_allocation':allocation,
                            'academic_session':'Autumn 2026-27','exam_type':'End Term Examination',
                            'source_status':'draft_unreviewed','applicability':'all_programmes_course_assignment_not_student_specific',
                            'evidence':_evidence(path,source_hash,page_number,f'Annexure-II room row {row_number}',quote)})
    if not records:
        raise ValueError('No course or department venue records were extracted from ETE Annexure-II.')
    return records


def _date_parts(date_text):
    matches=list(DATE_DMY.finditer(date_text))
    dates=[_iso_dmy(match.group(0)) for match in matches]
    ranges=[]
    for left,right in zip(matches,matches[1:]):
        separator=date_text[left.end():right.start()]
        if re.search(r'[-–]\s*$',separator):
            ranges.append([_iso_dmy(left.group(0)),_iso_dmy(right.group(0))])
    month_range=DATE_MONTH_RANGE.search(date_text)
    if month_range:
        values=month_range.groupdict()
        start_month=MONTHS[values['start_month'].casefold()]
        end_month=MONTHS[(values['end_month'] or values['start_month']).casefold()]
        year=int(values['year'])
        start=datetime(year,start_month,int(values['start_day'])).date().isoformat()
        end=datetime(year,end_month,int(values['end_day'])).date().isoformat()
        dates=[start,end]
        ranges=[[start,end]]
    elif not matches:
        month_matches=list(DATE_MONTH.finditer(date_text))
        dates=[datetime.strptime(' '.join(match.groups()),'%B %d %Y').date().isoformat()
               for match in month_matches]
    if re.search(r'\bOR\b',date_text,re.I):
        relation='tentative_alternatives'
    elif ranges:
        relation='date_ranges'
    elif len(dates)>1:
        relation='multiple_dates_source_format_preserved'
    elif dates:
        relation='single_date'
    else:
        relation='date_not_parsed'
    return dates,ranges,relation


def _calendar_kind(title):
    low=title.casefold()
    if 'examination' in low or 'exams' in low:
        return 'examination'
    if 'last date' in low:
        return 'deadline'
    if 'class' in low or 'teaching' in low:
        return 'teaching'
    if any(term in low for term in ('registration','orientation','admission')):
        return 'registration'
    if any(term in low for term in ('convocation','sangram','thomso','foundation day')):
        return 'institute_event'
    if any(term in low for term in ('vacation','holiday')):
        return 'holiday_or_break'
    return 'academic_milestone'


def _calendar_record(source, source_hash, page, locator, title, date_text, day_text,
                     status='source_provided_unreviewed', relation_override=None):
    title=_clean(title);date_text=_clean(date_text);day_text=_clean(day_text)
    dates,ranges,relation=_date_parts(date_text)
    if relation_override:
        relation=relation_override
    tentative=relation=='tentative_alternatives' or 'tentative' in title.casefold() or '#' in title
    source_note=None
    if '#' in title and 'convocation' in title.casefold():
        source_note='The calendar footnote says the final Convocation date will be notified in due course.'
    elif '*' in title:
        source_note='The calendar marks this event as subject to JoSAA counseling.'
    return {'record_id':_stable_id('academic-calendar',source_hash,page,locator),
            'title':title,'event_type':_calendar_kind(title),'date_text':date_text,
            'dates':dates,'date_ranges':ranges,'date_relation':relation,'day_text':day_text or None,
            'academic_session':'Autumn 2026-27','programme_scope':'All programs other than MBA',
            'source_status':'tentative_source_provided' if tentative else status,
            'applicability':'source_calendar_all_programmes_except_MBA_not_cohort_specific',
            'source_note':source_note,
            'evidence':_evidence(source,source_hash,page,locator,title+' | '+date_text+' | '+day_text)}


def _calendar_main_rows(source, source_hash, pdf):
    page=pdf.pages[0]
    tables=page.extract_tables() or []
    table=max(tables,key=len,default=[])
    if not table or not any('Details' in str(c or '') for row in table[:3] for c in row):
        raise ValueError('Could not locate the academic-calendar milestones table on page 1.')
    records=[];current=None
    def flush():
        if current is None: return
        title=' '.join(current['titles'])
        date_text=' '.join(current['dates'])
        day_text=' '.join(current['days'])
        records.append(_calendar_record(source,source_hash,1,
            f"calendar item {current['serial']}",title,date_text,day_text,
            relation_override='tentative_alternatives' if current['serial']==12 else None))
    for row in table:
        cells=[_clean(cell) for cell in row]
        serial=None
        for cell in cells[:3]:
            if cell.isdigit() and 1<=int(cell)<=35:
                serial=int(cell);break
        if serial is not None:
            flush()
            current={'serial':serial,'titles':[],'dates':[],'days':[]}
        if current is None:
            continue
        if any('Details' in cell or cell=='S.N.' for cell in cells):
            continue
        detail=' '.join(cell for cell in cells[3:6] if cell)
        date=' '.join(cell for cell in cells[6:9] if cell)
        day=' '.join(cell for cell in cells[9:] if cell)
        if detail: current['titles'].append(detail)
        if date: current['dates'].append(date)
        if day: current['days'].append(day)
    flush()
    if len(records)!=35:
        raise ValueError(f'Expected 35 academic-calendar milestone rows; extracted {len(records)}.')
    return records


def _calendar_page_two(source, source_hash, pdf):
    page=pdf.pages[1]
    text=page.extract_text() or ''
    records=[]
    # Page 2 repeats the key events/non-teaching periods alongside the teaching-day grid.
    # Preserve those exact source lines as separate citations rather than relying on page 1 alone.
    if 'Feedback/Response Form - I' in text and 'List of Holidays' in text:
        segment=text.split('Feedback/Response Form - I',1)[1].split('List of Holidays',1)[0]
        month_pattern=re.compile(r'(?i)\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}')
        for position,line in enumerate(segment.splitlines(),1):
            line=_clean(line)
            match=month_pattern.search(line)
            if not match:
                continue
            title=line[:match.start()].strip()
            date_text=line[match.start():].strip()
            if not title or not re.search(r'20\d{2}',date_text):
                continue
            relation='tentative_alternatives' if 'convocation' in title.casefold() else 'source_text_preserved'
            record=_calendar_record(source,source_hash,2,f'events and non-teaching list row {position}',
                                    title,date_text,'',relation_override=relation)
            record['event_type']='calendar_chart_entry'
            record['source_relation']='duplicate_calendar_chart_listing'
            records.append(record)
        summary_text='Feedback/Response Form - I '+segment
        records.append({'record_id':_stable_id('calendar-page-summary',source_hash,2,'events-non-teaching-list'),
            'title':'Autumn 2026-27 events and non-teaching days list',
            'event_type':'events_non_teaching_summary','date_text':None,'dates':[],'date_ranges':[],
            'date_relation':'source_text_preserved','day_text':None,'academic_session':'Autumn 2026-27',
            'programme_scope':'All programs other than MBA',
            'source_status':'source_provided_unreviewed',
            'applicability':'source_calendar_all_programmes_except_MBA_not_cohort_specific',
            'summary_text':summary_text[:1800],
            'evidence':_evidence(source,source_hash,2,'events and non-teaching days list',summary_text)})
    # Calendar chart has extra schedule changes that are absent from the milestones table.
    sections=(('Time-Table Rescheduling (for all programs)','Compensatory classes',
               'class_timetable_rescheduling'),
              ('Compensatory classes (only for UG I year courses)','Feedback/Response Form',
               'ug_first_year_compensatory_class'))
    for start_label,end_label,kind in sections:
        if start_label not in text:
            continue
        segment=text.split(start_label,1)[1].split(end_label,1)[0]
        for position,line in enumerate(segment.splitlines(),1):
            line=_clean(line)
            match=re.match(r'(.+?20\d{2})\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(.+)$',line,re.I)
            if not match:
                continue
            date_text=match.group(1);day=match.group(2).capitalize();action=match.group(3).strip()
            iso=_month_date(date_text)
            if not iso:
                continue
            title=('Timetable rescheduled: '+action if kind=='class_timetable_rescheduling'
                   else 'Compensatory UG Year I class: '+action)
            record=_calendar_record(source,source_hash,2,f'{kind} row {position}',title,date_text,day)
            record['event_type']=kind;record['timetable_action']=action
            records.append(record)
    # The chart lists holidays separately; preserve those exact records and note the moon caveat.
    if 'List of Holidays' in text:
        segment=text.split('List of Holidays',1)[1]
        for position,line in enumerate(segment.splitlines(),1):
            line=_clean(line)
            match=re.match(r'(.+?)\s+(\d{2}\.\d{2}\.\d{4})\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',line,re.I)
            if not match:
                continue
            title=match.group(1).strip().rstrip('*').strip()
            date=match.group(2);day=match.group(3).capitalize()
            record=_calendar_record(source,source_hash,2,f'holiday row {position}',title,date,day)
            record['event_type']='holiday'
            if '*' in match.group(1):
                record['source_note']='Source marks this holiday date subject to change with moon visibility.'
            records.append(record)
    # Keep the teaching-day grid as a searchable source excerpt without transcribing ambiguous cells.
    excerpt=text.split('*Time-Table Rescheduling',1)[0].strip()
    if excerpt:
        records.append({'record_id':_stable_id('calendar-grid-summary',source_hash,2,'teaching-days-grid'),
            'title':'Autumn 2026-27 teaching-days chart',
            'event_type':'teaching_days_summary','date_text':None,'dates':[],'date_ranges':[],
            'date_relation':'not_applicable','day_text':None,'academic_session':'Autumn 2026-27',
            'programme_scope':'All programs other than MBA',
            'source_status':'source_provided_unreviewed',
            'applicability':'source_calendar_all_programmes_except_MBA_not_cohort_specific',
            'summary_text':excerpt[:3000],
            'evidence':_evidence(source,source_hash,2,'teaching-days chart',excerpt)})
    return records


def extract_calendar_records(path=CALENDAR_SOURCE):
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError('Install ingestion/requirements.txt to parse the academic calendar PDF (pdfplumber is required).') from exc
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Academic calendar PDF not found: {path}')
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages)<2:
            raise ValueError('The Autumn 2026-27 academic calendar is incomplete.')
        first_text=pdf.pages[0].extract_text() or ''
        if 'All Programs (Other than MBA)' not in first_text:
            raise ValueError('Calendar applicability label is missing or differs from expected source.')
        records=_calendar_main_rows(path,source_hash,pdf)
        records.extend(_calendar_page_two(path,source_hash,pdf))
    if not records or any(not item['evidence'].get('page') or not item['evidence'].get('source_version_id') for item in records):
        raise ValueError('Academic calendar records must retain page and source hash evidence.')
    return records


def extract_all():
    return {'ete':extract_ete_records(),'calendar':extract_calendar_records()}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Import the ETE schedule and Autumn 2026-27 academic calendar.')
    parser.add_argument('--write-ete-snapshot',action='store_true',
        help='Create the checksummed, roster-free JSON snapshot from the local original ETE PDF.')
    args=parser.parse_args()
    ete=extract_ete_records()
    if args.write_ete_snapshot:
        write_ete_snapshot(ete)
    result={'ete':ete,'calendar':extract_calendar_records()}
    print(json.dumps({'ete_records':len(result['ete']),'calendar_events':len(result['calendar']),
        'ete_course_codes':len({r['course_code'] for r in result['ete'] if r.get('course_code')}),
        'ete_pages':sorted({r['evidence']['page'] for r in result['ete']})},indent=2))
