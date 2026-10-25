from collections import Counter
import unittest
from bot.catalogue import Catalogue, link


class CatalogueTests(unittest.TestCase):
    def setUp(self): self.catalogue = Catalogue()

    def test_years_cover_every_identity_and_leave_unassigned_options_separate(self):
        c = self.catalogue
        groups = {y:c.year_courses(y) for y in ('1','2','3','4','options')}
        self.assertEqual(len({row['course_id'] for rows in groups.values() for row in rows}),120)
        self.assertTrue(all(not c.semesters(row) for row in groups['options']))
        self.assertTrue(all(any(s in (3,4) for s in c.semesters(row)) for row in groups['2']))
        with self.assertRaises(ValueError): c.year_courses('5')

    def test_codes_do_not_alias_different_curricula(self):
        c = self.catalogue.course('ecc203')
        self.assertIn('Electromagnetics',c['title'])
        self.assertIn('Semester: 3',self.catalogue.course_details(c))
        self.assertIsNone(self.catalogue.course('unknown-999'))

    def test_workbook_courses_are_browsable_and_source_labelled(self):
        c=self.catalogue
        self.assertTrue(any(row['code']=='DAE-101' for row in c.year_courses('2')))
        self.assertTrue(any(row['code']=='ECL-316' for row in c.year_courses('options')))
        self.assertTrue(any(row['code']=='ECO-101' for row in c.year_courses('options')))
        year_two=c.year_overview('2')
        self.assertIn('DAE-101',year_two)
        self.assertIn('View supplied curriculum',year_two)
        self.assertIn('ECE_Course_Structure.xlsx (user-supplied; applicability not verified)',year_two)
        detail=c.course_details(c.course('ECO-101'))
        self.assertIn('ECE_Course_Structure.xlsx',detail)
        self.assertIn('Credits: 3',detail)

    def test_source_links_are_safe_and_text_escaped(self):
        self.assertEqual(link('<test>', 'javascript:alert(1)'), '&lt;test&gt;')
        self.assertIn('&amp;',link('A & B','https://example.org/?a=1&b=2'))

    def test_unknown_and_ambiguous_resource_ids_cannot_be_rendered(self):
        hits = [{'metadata':{'entity_id':'invented'}},{'metadata':{'entity_id':'razavi-fundamentals-2:chapter:17'}}]
        self.assertIn('couldn’t find',self.catalogue.render_hits(hits))

    def test_resources_deduplicate_and_fit_telegram_message_limit(self):
        c = self.catalogue
        ids = list(c.books)+list(c.lectures)
        output = c.render_hits([{'metadata':{'entity_id':id}} for id in ids+ids])
        self.assertEqual(output.count('<b>Read</b>'),2)
        self.assertEqual(output.count('<b>Watch</b>'),2)
        self.assertLess(len(output),4096)
        for faculty in c.faculty.values():
            rendered = c.render_hits([{'metadata':{'entity_id':faculty['faculty_id']}}],True)
            self.assertIn('supervision',rendered)
            self.assertLess(len(rendered),1800)


if __name__=='__main__': unittest.main()
