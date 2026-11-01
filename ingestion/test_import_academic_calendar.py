"""Focused integrity checks for the supplied calendar PDFs."""
import re
import hashlib
import tempfile
import unittest
from pathlib import Path

from ingestion.import_academic_calendar import (
    ETE_SOURCE, ROOT, extract_calendar_records, extract_ete_records, load_ete_snapshot,
)


class AcademicCalendarImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ete=extract_ete_records()
        cls.calendar=extract_calendar_records()

    def test_ete_records_keep_exact_course_time_room_slot_and_draft_status(self):
        rows=[row for row in self.ete if row.get('course_code')=='ECC-201']
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual((row['exam_date'],row['day']),('2026-11-14','Saturday'))
        self.assertEqual((row['start_time'],row['end_time']),('14:30','17:45'))
        self.assertEqual((row['slot'],row['room']),('C1','GB-202'))
        self.assertEqual(row['source_status'],'draft_unreviewed')
        self.assertEqual(row['evidence']['page'],11)

    def test_ete_roster_pages_and_student_identifiers_are_not_imported(self):
        self.assertTrue(self.ete)
        self.assertTrue(all(5<=row['evidence']['page']<=30 for row in self.ete))
        content=' '.join(' '.join(str(row.get(field) or '') for field in
            ('record_type','course_code','department_name','room','programme_allocation'))
            +' '+str(row['evidence'].get('quote') or '') for row in self.ete)
        self.assertNotRegex(content,r'\bEnrollment\s*No\b')
        self.assertNotRegex(content,r'\b\d{8}\b')

    def test_safe_snapshot_fallback_matches_pdf_extraction_without_touching_original(self):
        snapshot=load_ete_snapshot()
        missing_source=ROOT/'data'/'source_not_present_in_clean_clone.pdf'
        self.assertFalse(missing_source.exists())
        original_hash=(hashlib.sha256(ETE_SOURCE.read_bytes()).hexdigest()
                       if ETE_SOURCE.is_file() else None)
        fallback=extract_ete_records(path=missing_source)
        self.assertEqual(fallback,self.ete)
        self.assertEqual(snapshot['source']['sha256'],self.ete[0]['evidence']['source_version_id'])
        if original_hash:
            self.assertEqual(hashlib.sha256(ETE_SOURCE.read_bytes()).hexdigest(),original_hash)

    def test_safe_snapshot_checksum_is_verified(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            snapshot=Path(directory)/'safe.json'
            snapshot.write_text('{}',encoding='utf-8')
            checksum=Path(directory)/'safe.sha256'
            checksum.write_text('0'*64+'  safe.json\n',encoding='ascii')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                load_ete_snapshot(snapshot_path=snapshot)

    def test_calendar_includes_milestones_holidays_adjustments_and_page_two_events(self):
        kinds={row['event_type'] for row in self.calendar}
        self.assertTrue({'examination','holiday','class_timetable_rescheduling',
                         'ug_first_year_compensatory_class','events_non_teaching_summary',
                         'teaching_days_summary'}<=kinds)
        self.assertEqual(sum(row['event_type']=='class_timetable_rescheduling' for row in self.calendar),2)
        self.assertEqual(sum(row['event_type']=='ug_first_year_compensatory_class' for row in self.calendar),4)
        sept23=next(row for row in self.calendar if row.get('date_text')=='September 23, 2026')
        self.assertEqual(sept23['dates'],['2026-09-23'])
        self.assertEqual(sept23['date_relation'],'single_date')
        self.assertEqual(sum(row['event_type']=='holiday' for row in self.calendar),11)
        summary=next(row for row in self.calendar if row['event_type']=='events_non_teaching_summary')
        self.assertIn('Mid Term Examination September 10',summary['summary_text'])
        teaching=next(row for row in self.calendar if row['event_type']=='teaching_days_summary')
        self.assertIn('72 for others',teaching['summary_text'])
        self.assertTrue(all(row['programme_scope']=='All programs other than MBA' for row in self.calendar))
        self.assertTrue(all(row['evidence']['page'] in (1,2) for row in self.calendar))

    def test_conditional_and_tentative_footnotes_are_preserved(self):
        convocation=[row for row in self.calendar if row['title'].startswith('Convocation 2026 #')]
        self.assertEqual(len(convocation),1)
        self.assertEqual(convocation[0]['source_status'],'tentative_source_provided')
        self.assertIn('final Convocation date',convocation[0]['source_note'])
        ug_dates=[row for row in self.calendar if 'Commencement of Classes for UG I year' in row['title']]
        self.assertEqual(len(ug_dates),1)
        self.assertIn('JoSAA counseling',ug_dates[0]['source_note'])
        milad=[row for row in self.calendar if row['title'].startswith('Id-e-Milad')]
        self.assertEqual(len(milad),1)
        self.assertIn('moon visibility',milad[0]['source_note'])


if __name__=='__main__':
    unittest.main()
