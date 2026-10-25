"""Source import integrity for the workbook and recurring timetable."""
import hashlib
import unittest
from import_course_workbook import WORKBOOK, course_text, extract_records
from import_timetable import SOURCE, extract_records as extract_timetable
from import_course_faculty import SOURCE as FACULTY_SOURCE, extract_records as extract_course_faculty


class SourceImportTests(unittest.TestCase):
    def test_course_workbook_sheets_and_provenance_are_preserved(self):
        records=extract_records()
        source_hash=hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
        self.assertEqual(len(records),127)
        self.assertEqual(len({record['code'] for record in records}),111)
        self.assertEqual(sum(record['category']=='curriculum_course' for record in records),53)
        self.assertTrue(all(record['evidence']['source_version_id']==source_hash for record in records))
        self.assertTrue(all(record['evidence']['locator'] for record in records))
        course=next(record for record in records if record['code']=='ECC-101')
        self.assertEqual((course['year'],course['semester'],course['term']),(1,1,'Autumn'))
        elective=next(record for record in records if record['code']=='ECL-316')
        self.assertEqual(elective['category'],'program_elective')
        self.assertIsNone(elective['year'])
        self.assertNotIn('@',course_text(elective))

    def test_timetable_import_retains_221_rows_and_separate_group_fields(self):
        records=extract_timetable()
        source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(len(records),221)
        self.assertTrue(all(record['evidence']['source_version_id']==source_hash for record in records))
        self.assertTrue(all(record['evidence']['page'] for record in records))
        hsi=next(record for record in records if record['course_code']=='HSI-101')
        self.assertEqual(hsi['course_batch'],'5')
        self.assertEqual(hsi['student_sections'],['26EC1','26EC2','26EC3','26EC4'])
        year_four=[record for record in records if record['study_year']==4]
        self.assertTrue(all(not record['student_sections'] for record in year_four))

    def test_course_professor_override_has_team_note_provenance(self):
        assignments=extract_course_faculty()
        source_hash=hashlib.sha256(FACULTY_SOURCE.read_bytes()).hexdigest()
        self.assertEqual(len(assignments),1)
        self.assertEqual((assignments[0]['course_code'],assignments[0]['faculty_name']),
                         ('ECT-108','Saurabh Khanna'))
        self.assertEqual(assignments[0]['role'],'Professor')
        self.assertEqual(assignments[0]['applicability'],'user_supplied_unverified')
        self.assertEqual(assignments[0]['evidence']['source_version_id'],source_hash)
        self.assertTrue(assignments[0]['faculty_id'])


if __name__=='__main__': unittest.main()
