"""Deterministic, provenance-aware answers from the supplied calendar PDFs."""
from collections import defaultdict
from datetime import date
from html import escape
import json
import re
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datafiles/academic'
MONTH_NUMBER={name.casefold():number for number,name in enumerate(
    ('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTH_NUMBER.update({'jan':1,'feb':2,'mar':3,'apr':4,'jun':6,'jul':7,'aug':8,
                     'sep':9,'sept':9,'oct':10,'nov':11,'dec':12})
MONTH_DATE_QUERY=re.compile(
    r'(?i)\b(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|July|Jul|August|Aug|'
    r'September|Sept|Sep|October|Oct|November|Nov|December|Dec)\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b')


def _words(value):
    words=re.findall(r'[a-z0-9]+',str(value or '').casefold())
    normalized=[];index=0
    while index<len(words):
        if index+1<len(words) and words[index:index+2] in (
                ['mid','term'],['mid','semester'],['end','term'],['end','semester']):
            normalized.append('midterm' if words[index]=='mid' else 'endterm');index+=2
        else:
            normalized.append(words[index]);index+=1
    return set(normalized)


def _query_dates(text):
    """Extract explicit ISO, DMY, or named month/day dates from a question."""
    value=str(text or '')
    result=set()
    for year,month,day in re.findall(r'\b(20\d{2})-(\d{2})-(\d{2})\b',value):
        try: result.add(('date',date(int(year),int(month),int(day))))
        except ValueError: pass
    for day,month,year in re.findall(r'\b(\d{2})\.(\d{2})\.(20\d{2})\b',value):
        try: result.add(('date',date(int(year),int(month),int(day))))
        except ValueError: pass
    for month_name,day,year in MONTH_DATE_QUERY.findall(value):
        month=MONTH_NUMBER[month_name.casefold()]
        try:
            if year: result.add(('date',date(int(year),month,int(day))))
            else: result.add(('month_day',(month,int(day))))
        except ValueError: pass
    return result


def _record_matches_dates(record,query_dates):
    dates=[]
    for value in record.get('dates',[]):
        try: dates.append(date.fromisoformat(value))
        except (TypeError,ValueError): pass
    ranges=[]
    for pair in record.get('date_ranges',[]):
        if len(pair)!=2: continue
        try: ranges.append((date.fromisoformat(pair[0]),date.fromisoformat(pair[1])))
        except (TypeError,ValueError): pass
    for kind,value in query_dates:
        if kind=='date':
            if value in dates or any(start<=value<=end for start,end in ranges):
                return True
        else:
            month,day=value
            if any(item.month==month and item.day==day for item in dates):
                return True
            for start,end in ranges:
                for year in range(start.year,end.year+1):
                    try: candidate=date(year,month,day)
                    except ValueError: continue
                    if start<=candidate<=end:
                        return True
    return False


class AcademicSchedule:
    """Read imported source records; exact course/date facts never come from an LLM."""
    def __init__(self, ete_path=None, calendar_path=None):
        self.ete_path=Path(ete_path or DATA/'ete_schedule_records.json')
        self.calendar_path=Path(calendar_path or DATA/'academic_calendar_events.json')
        self.ete=self._read(self.ete_path)
        self.calendar=self._read(self.calendar_path)
        self.ete_by_course=defaultdict(list)
        for record in self.ete:
            if record.get('course_code'):
                self.ete_by_course[record['course_code'].upper()].append(record)

    @staticmethod
    def _read(path):
        if not path.is_file():
            return []
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,list):
            raise ValueError(f'Academic schedule file must contain a record list: {path.name}')
        return value

    def match_course_code(self,text):
        upper=str(text or '').upper()
        codes=sorted(self.ete_by_course,key=len,reverse=True)
        return next((code for code in codes if re.search(
            r'(?<![A-Z0-9])'+re.escape(code)+r'(?![A-Z0-9])',upper)),None)

    @staticmethod
    def is_query(text):
        lower=str(text or '').casefold()
        if _query_dates(text):
            return True
        if re.search(r'\b(?:academic\s+calendar|calendar\s+dates?|holidays?|public holidays?)\b',lower):
            return True
        date_intent=bool(re.search(r'\b(?:when|date|dates|time|schedule|calendar|upcoming|tomorrow|today)\b',lower))
        exam_period=bool(re.search(
            r'\b(?:ete|end[-\s]*term|mid[-\s]*(?:term|semester)|midsem(?:ester)?|mte|final exams?)\b',lower))
        if exam_period:
            return date_intent or bool(re.search(r'\b(?:exam|examination)\b',lower))
        return bool(re.search(r'\b(?:exam|examination)s?\b',lower)
                    and date_intent)

    @staticmethod
    def _source(record):
        evidence=record.get('evidence',{})
        name=Path(evidence.get('path','source PDF')).name
        page=evidence.get('page')
        return f'{name}'+(f', page {page}' if page else '')

    @staticmethod
    def _fmt_date(value):
        if not value:
            return 'date not stated'
        return value

    def render_calendar_overview(self):
        if not self.calendar:
            return 'The Autumn academic calendar has not been imported yet. Run the source pipeline first.'
        important=[record for record in self.calendar
                   if record.get('event_type')=='examination']
        important += [record for record in self.calendar
                      if record.get('event_type')=='deadline' and
                      any(word in record.get('title','').casefold()
                          for word in ('adding/changing','last date of teaching','withdrawal'))]
        lines=['<b>Autumn 2026–27 academic dates</b>',
               'The supplied calendar is for all programs other than MBA; cohort applicability has not been separately confirmed.']
        for record in important:
            lines.append(f"• {escape(record['title'])}: {escape(record.get('date_text') or 'date not stated')} "
                         f"<i>({escape(self._source(record))})</i>")
            if record.get('source_note'):
                lines.append('  '+escape(record['source_note']))
        ete_records=[record for record in self.ete if record.get('record_type')=='course_exam']
        if ete_records:
            lines += ['', 'A separate course-by-course ETE PDF is explicitly a draft. Its detailed entries cover November 13–21 only; the calendar period continues through November 24, so detailed assignments for November 23–24 are not included. Ask for an exact course code, such as “When is ECC-201 ETE?” to see its listed time and room.']
        else:
            lines += ['', 'A course-by-course ETE schedule has not been imported.']
        lines += ['', 'These records are copied from supplied PDFs, not independently confirmed against a live update.']
        return '\n'.join(lines)

    def render_holidays(self):
        holidays=[record for record in self.calendar if record.get('event_type')=='holiday']
        if not holidays:
            return self.render_calendar_overview()
        lines=['<b>Holidays listed in the Autumn 2026–27 calendar</b>']
        for record in sorted(holidays,key=lambda item:(item.get('dates') or ['9999'])[0]):
            day=record.get('day_text') or 'weekday not stated'
            note=' · date is subject to change per the source note' if record.get('source_note') else ''
            lines.append(f"• {escape(record['title'])} · {escape(record.get('date_text') or day)}{escape(note)} "
                         f"<i>({escape(self._source(record))})</i>")
        lines += ['', 'The academic calendar states that the Id-e-Milad date may change with moon visibility.']
        return '\n'.join(lines)

    def render_exam_course(self,course_code):
        code=course_code.upper()
        rows=sorted(self.ete_by_course.get(code,[]),key=lambda row:(row['exam_date'],row['start_time'],row['room'] or ''))
        if not rows:
            return (f'No {escape(code)} entry was found in the supplied draft ETE schedule. '
                    'The imported course-by-course assignments cover November 13–21 only, while the calendar lists end-term exams through November 24; detailed course assignments for November 23–24 remain unresolved. '
                    'That absence does not confirm the course has no exam; verify against the latest examination notice.')
        lines=[f'<b>{escape(code)} · Autumn 2026–27 ETE schedule (DRAFT)</b>']
        for row in rows:
            slot=f" · slot {escape(str(row['slot']))}" if row.get('slot') else ''
            allocation=f" · printed program/range allocation {escape(row['programme_allocation'])}" if row.get('programme_allocation') else ''
            lines.append(f"• {escape(row['exam_date'])} ({escape(row['day'])}) · "
                         f"{escape(row['start_time'])}–{escape(row['end_time'])} Asia/Kolkata{slot} · "
                         f"room {escape(row['room'] or 'not stated')}{allocation} "
                         f"<i>({escape(self._source(row))})</i>")
        lines += ['', 'The PDF is labelled draft. Printed program/enrollment ranges are not a verified match to an individual student or section; confirm your assignment from the latest official notice.']
        return '\n'.join(lines)

    def _matching_calendar_events(self,text):
        lower=str(text or '').casefold()
        if re.search(r'\bholidays?|public holidays?\b',lower):
            return [record for record in self.calendar if record.get('event_type')=='holiday']
        query_dates=_query_dates(text)
        if query_dates:
            return [record for record in self.calendar
                    if record.get('event_type') not in ('teaching_days_summary','calendar_chart_entry','events_non_teaching_summary')
                    and _record_matches_dates(record,query_dates)]
        terms=_words(lower)
        if 'ete' in terms or 'endterm' in terms:
            terms.add('endterm')
        if 'mte' in terms or 'midsem' in terms or 'midsemester' in terms or 'mid' in terms and ('term' in terms or 'semester' in terms):
            terms.add('midterm')
        scored=[]
        for record in self.calendar:
            if record.get('event_type') in ('teaching_days_summary','calendar_chart_entry','events_non_teaching_summary'):
                continue
            title_terms=_words(record.get('title',''))
            if 'ete' in terms or 'endterm' in terms:
                if 'endterm' not in title_terms or record.get('event_type')!='examination':
                    continue
                score=100
            elif 'midterm' in terms:
                if 'midterm' not in title_terms or record.get('event_type')!='examination':
                    continue
                score=100
            else:
                score=len(terms & title_terms)
            if score:
                scored.append((score,record))
        return [record for _,record in sorted(scored,key=lambda item:(-item[0],item[1].get('date_text','')))[:5]]

    def reply(self,text,selected_course=None):
        midterm_intent=bool(re.search(r'\b(?:mte|mid[-\s]*(?:term|semester)|midsem(?:ester)?)\b',text,re.I))
        exam_intent=bool(re.search(r'\b(?:ete|end[-\s]*term|exam|examination|mte|mid[-\s]*(?:term|semester)|midsem(?:ester)?)\b',text,re.I))
        explicit_code=re.search(r'(?<![A-Z0-9])([A-Z]{2,5}-\d{3})(?![A-Z0-9])',text,re.I)
        code=self.match_course_code(text) or (explicit_code.group(1).upper() if explicit_code else None)
        code=code or (selected_course if exam_intent else None)
        if code and exam_intent and not midterm_intent:
            return self.render_exam_course(code)
        query_dates=_query_dates(text)
        if query_dates:
            matches=self._matching_calendar_events(text)
            if not matches:
                return 'The supplied calendar has no matching entry for that date.'
            lines=['<b>Calendar entries matching that date</b>']
            for record in matches:
                lines.append(f"• {escape(record['title'])}: {escape(record.get('date_text') or 'date not stated')} "
                             f"<i>({escape(self._source(record))})</i>")
                if record.get('source_note'):
                    lines.append('  '+escape(record['source_note']))
            if (('month_day',(11,23)) in query_dates or ('month_day',(11,24)) in query_dates
                    or ('date',date(2026,11,23)) in query_dates
                    or ('date',date(2026,11,24)) in query_dates):
                lines += ['', 'The broad ETE period includes this date, but detailed course assignments were only imported through November 21; verify the latest official notice.']
            return '\n'.join(lines)
        if re.search(r'\bholidays?|public holidays?\b',text,re.I):
            return self.render_holidays()
        if re.search(r'\b(?:ete|end[-\s]*term|exam|examination|mte|mid[-\s]*(?:term|semester)|midsem(?:ester)?)\b',text,re.I):
            matches=self._matching_calendar_events(text)
            if matches:
                lines=['<b>Exam dates in the supplied Autumn 2026–27 calendar</b>']
                for record in matches:
                    lines.append(f"• {escape(record['title'])}: {escape(record.get('date_text') or 'date not stated')} "
                                 f"<i>({escape(self._source(record))})</i>")
                lines += ['', 'The calendar gives broad exam periods. The separate course-by-course ETE file is a draft; provide a course code to see its listed time and room.']
                return '\n'.join(lines)
            return ('I can show the calendar’s broad exam periods, but it does not identify your personal course assignment. '
                    'Send a course code, such as “When is ECC-201 ETE?”, for a lookup in the draft course schedule.\n\n'
                    +self.render_calendar_overview())
        matches=self._matching_calendar_events(text)
        if matches:
            lines=['<b>Matching Autumn 2026–27 calendar entries</b>']
            for record in matches:
                lines.append(f"• {escape(record['title'])}: {escape(record.get('date_text') or 'date not stated')} "
                             f"<i>({escape(self._source(record))})</i>")
                if record.get('source_status')=='tentative_source_provided':
                    lines.append('  The source marks this date as tentative or gives alternatives.')
                if record.get('source_note'):
                    lines.append('  '+escape(record['source_note']))
            lines += ['', 'The supplied calendar covers all programs other than MBA; these records have not been checked against a live update.']
            return '\n'.join(lines)
        if re.search(r'\b(?:calendar|academic dates?)\b',text,re.I):
            return self.render_calendar_overview()
        return ('I could not identify a matching academic-calendar item in the supplied source. '
                'Try “academic calendar”, “holidays”, “mid-term dates”, “ETE schedule”, or include a course code.')
