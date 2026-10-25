"""Exact timetable lookup and conversation flow; no model or API required."""
import unittest
from bot.assistant import StudyAssistant
from bot.catalogue import Catalogue
from bot.conversation import Conversation


class SpyRetriever:
    def __init__(self): self.calls=[]
    def search(self,*args,**kwargs): self.calls.append((args,kwargs)); return []


class TimetableTests(unittest.TestCase):
    def setUp(self):
        self.catalogue=Catalogue()
        self.retriever=SpyRetriever()
        self.chat=Conversation(StudyAssistant(self.retriever,self.catalogue))
        self.timetable=self.catalogue.timetable

    def test_imported_rows_keep_year_sections_and_course_batch_distinct(self):
        self.assertEqual(len(self.timetable.rows),221)
        self.assertEqual({year:len(self.timetable.for_year(year)) for year in ('1','2','3','4')},
                         {'1':46,'2':46,'3':59,'4':70})
        first=next(row for row in self.timetable.rows if row.get('course_code')=='HSI-101')
        self.assertEqual(first['course_batch'],'5')
        self.assertEqual(first['student_sections'],['26EC1','26EC2','26EC3','26EC4'])

    def test_section_and_timetable_batch_filters_are_exact(self):
        rows=self.timetable.matching('1',section='26EC1',batch='5')
        self.assertTrue(rows)
        self.assertTrue(all('26EC1' in row['student_sections'] for row in rows))
        self.assertTrue(all(row['course_batch']=='5' for row in rows))

    def test_personal_timetable_asks_year_then_section_and_skips_unscoped_rows(self):
        self.assertIn('Which study year',self.chat.reply('show my timetable'))
        self.assertIn('25EC1',self.chat.reply('2'))
        reply=self.chat.reply('25EC1')
        self.assertIn('Year 2 timetable',reply)
        self.assertIn('ECC-205',reply)
        self.assertNotIn('student section not recorded',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_informal_year_and_ece_batch_phrase_resolves_student_section(self):
        reply=self.chat.reply('I am a 2nd year from ECE-3 batch, please show my timetable')
        self.assertIn('Year 2 timetable · 25EC3',reply)
        self.assertNotIn('Which student section?',reply)
        self.assertIsNone(self.chat.state.get('timetable_batch'))
        self.assertTrue(all('25EC3' in row['student_sections']
                            for row in self.timetable.matching('2',section='25EC3')))
        self.assertEqual(self.retriever.calls,[])

    def test_informal_ece_batch_remembers_group_while_asking_year(self):
        first=self.chat.reply('I am from ECE-3 batch, can I see my timetable?')
        self.assertIn('Which study year',first)
        reply=self.chat.reply('second year')
        self.assertIn('Year 2 timetable · 25EC3',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_year_wide_schedule_labels_missing_scope_and_stays_deterministic(self):
        reply=self.chat.reply('show timetable for third year on Monday')
        self.assertIn('Monday',reply)
        self.assertIn('student section not recorded',reply)
        self.assertIn('OCR-extracted weekly entries',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_year_four_does_not_claim_personal_section_assignments(self):
        self.chat.reply('my timetable')
        reply=self.chat.reply('4')
        self.assertIn('no student-section labels',reply)
        self.assertIn('student section not recorded',reply)

    def test_unknown_section_does_not_fall_back_to_another_group(self):
        self.chat.reply('my timetable')
        self.chat.reply('2')
        reply=self.chat.reply('27EC9')
        self.assertIn('is not listed under Year 2',reply)
        self.assertIn('25EC1',reply)
        self.assertEqual(self.retriever.calls,[])


if __name__=='__main__': unittest.main()
