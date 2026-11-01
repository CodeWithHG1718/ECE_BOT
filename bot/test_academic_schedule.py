"""Deterministic answer behavior for imported exam/calendar records."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from bot.academic_schedule import AcademicSchedule
from bot.conversation import Conversation


def event(title,kind,date_text,date,source='calendar.pdf',page=1,status='source_provided_unreviewed',note=None):
    result={'record_id':title,'title':title,'event_type':kind,'date_text':date_text,
        'dates':[date] if date else [],'date_ranges':[],'date_relation':'single_date',
        'source_status':status,'source_note':note,
        'evidence':{'path':source,'page':page}}
    return result


def exam(code='ECC-201',date='2026-11-14',time='14:30',room='GB-202',allocation=None):
    return {'record_id':code+date,'record_type':'course_exam','course_code':code,
        'exam_date':date,'day':'Saturday','start_time':time,'end_time':'17:45','slot':'C1',
        'room':room,'programme_allocation':allocation,'source_status':'draft_unreviewed',
        'evidence':{'path':'Draft_Schedule_ETE_Autumn_2026-27.pdf','page':11}}


class AcademicScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        root=Path(self.temp.name)
        self.ete_path=root/'ete.json';self.calendar_path=root/'calendar.json'
        self.ete_path.write_text(json.dumps([exam(allocation='[ECE (1-67)]')]),encoding='utf-8')
        endterm=event('End Term Examinations (excluding Sunday and declared holidays)','examination',
                      '13.11.2026 -24.11.2026',None,page=1)
        endterm['dates']=['2026-11-13','2026-11-24']
        endterm['date_ranges']=[['2026-11-13','2026-11-24']]
        self.calendar_path.write_text(json.dumps([
            event('Mid-Term Examinations (except Sunday)','examination','10.09.2026 -15.09.2026',None,page=1),
            endterm,
            event('Independence Day','holiday','15.08.2026','2026-08-15',page=2),
            event('Timetable rescheduled: Fridays time table','class_timetable_rescheduling',
                  'September 23, 2026','2026-09-23',page=2),
        ]),encoding='utf-8')
        self.schedule=AcademicSchedule(self.ete_path,self.calendar_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_natural_course_exam_request_returns_exact_source_record(self):
        answer=self.schedule.reply('When is ECC-201 ETE?')
        self.assertIn('2026-11-14 (Saturday)',answer)
        self.assertIn('14:30–17:45 Asia/Kolkata',answer)
        self.assertIn('slot C1',answer)
        self.assertIn('room GB-202',answer)
        self.assertIn('DRAFT',answer)
        self.assertIn('not a verified match to an individual student',answer)

    def test_unknown_course_does_not_get_a_similar_course_answer(self):
        answer=self.schedule.reply('When is ECC-999 ETE?')
        self.assertIn('No ECC-999 entry',answer)
        self.assertNotIn('ECC-201',answer)
        self.assertIn('detailed course assignments for November 23–24 remain unresolved',answer)

    def test_midterm_calendar_query_returns_source_period(self):
        answer=self.schedule.reply('What are the mid-term examination dates?')
        self.assertIn('10.09.2026 -15.09.2026',answer)
        self.assertIn('calendar.pdf, page 1',answer)
        self.assertIn('course-by-course ETE file is a draft',answer)

    def test_mid_semester_synonym_selects_only_midterm_period(self):
        answer=self.schedule.reply('What are mid-semester examination dates?')
        self.assertIn('10.09.2026 -15.09.2026',answer)
        self.assertNotIn('Re-examination',answer)
        self.assertNotIn('End Term Examinations',answer)

    def test_holiday_query_returns_only_calendar_holidays(self):
        answer=self.schedule.reply('Show holidays')
        self.assertIn('Independence Day',answer)
        self.assertNotIn('Mid-Term Examinations',answer)

    def test_exam_intent_is_not_triggered_by_general_study_anxiety(self):
        self.assertFalse(self.schedule.is_query("I'm worried about my exam and don't know what to study."))

    def test_mid_semester_exam_dates_are_routed_to_calendar(self):
        self.assertTrue(self.schedule.is_query('What are mid-semester examination dates?'))

    def test_mte_synonym_selects_only_the_mid_term_calendar_record(self):
        self.assertTrue(self.schedule.is_query('What are MTE dates?'))
        answer=self.schedule.reply('What are MTE dates?',selected_course='ECC-201')
        self.assertIn('Mid-Term Examinations',answer)
        self.assertIn('10.09.2026 -15.09.2026',answer)
        self.assertNotIn('End Term Examinations',answer)
        self.assertNotIn('Re-examination',answer)
        self.assertNotIn('ECC-201',answer)

    def test_explicit_date_query_matches_rescheduled_entry(self):
        self.assertTrue(self.schedule.is_query('What happens on September 23?'))
        answer=self.schedule.reply('What happens on September 23?')
        self.assertIn('Timetable rescheduled',answer)
        self.assertIn('September 23, 2026',answer)
        self.assertIn('calendar.pdf, page 2',answer)

    def test_date_query_matches_normalized_range_and_discloses_detail_gap(self):
        answer=self.schedule.reply('What happens on November 23?')
        self.assertIn('End Term Examinations',answer)
        self.assertIn('detailed course assignments were only imported through November 21',answer)

    def test_shared_conversation_routes_natural_course_query_to_schedule(self):
        assistant=SimpleNamespace(catalogue=SimpleNamespace(academic_schedule=self.schedule),llm=None)
        answer=Conversation(assistant).structured_reply('When is ECC-201 ETE?')
        self.assertIn('2026-11-14 (Saturday)',answer)
        self.assertIn('Draft_Schedule_ETE_Autumn_2026-27.pdf, page 11',answer)

    def test_dates_command_uses_deterministic_calendar_overview(self):
        assistant=SimpleNamespace(catalogue=SimpleNamespace(academic_schedule=self.schedule),llm=None)
        answer=Conversation(assistant).structured_reply('/dates')
        self.assertIn('Autumn 2026',answer)
        self.assertIn('calendar.pdf, page 1',answer)

    def test_shared_conversation_routes_explicit_date_question(self):
        assistant=SimpleNamespace(catalogue=SimpleNamespace(academic_schedule=self.schedule),llm=None)
        answer=Conversation(assistant).structured_reply('What happens on September 23?')
        self.assertIn('Timetable rescheduled',answer)
        self.assertIn('calendar.pdf, page 2',answer)


if __name__=='__main__':
    unittest.main()
