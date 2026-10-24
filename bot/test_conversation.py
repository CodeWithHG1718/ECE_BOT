"""Regression coverage for actual student conversations; no model/API required."""
import json
import unittest
from bot.assistant import StudyAssistant
from bot.catalogue import Catalogue
from bot.conversation import Conversation, year_in
from bot.prompts import build_answer_messages, retrieval_topic, requested_academic_year
from bot.navigation import SECTIONS, ACTIONS, UNAVAILABLE


class SpyRetriever:
    def __init__(self): self.calls=[]
    def search(self,*args):
        self.calls.append(args)
        return []


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.retriever=SpyRetriever()
        self.catalogue=Catalogue()
        self.chat=Conversation(StudyAssistant(self.retriever,self.catalogue))

    def assert_complete_year(self,reply,year):
        self.assertIn(f'Year {year}',reply)
        self.assertIn(f'Semester {2*int(year)-1}',reply)
        self.assertIn(f'Semester {2*int(year)}',reply)
        for course in self.catalogue.year_courses(str(year)):
            self.assertIn(course['code']+' — ',reply)

    def test_reported_transcript_never_searches_raw_year_numbers(self):
        self.chat.welcome()
        reply=self.chat.reply('/courses 1-4')
        for year in range(1,5): self.assert_complete_year(reply,year)
        self.assert_complete_year(self.chat.reply('2'),2)
        reply=self.chat.reply('what are the main topics in 2nd year of ece in iit roorkee')
        self.assert_complete_year(reply,2)
        self.assertIn('Highlights:',reply)
        self.assertIn('options',self.chat.reply('/courses optio'))
        self.assert_complete_year(self.chat.reply('4'),4)
        self.assertEqual(self.retriever.calls,[])

    def test_natural_year_requests_list_every_code(self):
        for text in ('show me courses of 2nd year','second-year courses',
                     'subjects for year 2','show me courses of second year at IIT Roorkee in 2026'):
            with self.subTest(text=text):
                reply=self.chat.reply(text)
                self.assert_complete_year(reply,2)
                self.assertNotIn('Year 3',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_year_course_topic_followup_keeps_course_context(self):
        self.chat.reply('show me courses of 2nd year')
        self.assertIn('Highlights:',self.chat.reply('which topic should I study?'))
        reply=self.chat.reply('Network Theory')
        self.assertIn('ECC-205',reply)
        self.assertIn('Topics to study',reply)
        self.assertIn('Related syllabus:',reply)
        first=self.chat.state['topic_choices'][0]
        self.chat.reply('1')
        self.assertEqual(self.retriever.calls[0][0],first.split(':',1)[0] if ':' in first else first[:900])
        self.assertTrue(all(call[1]=='ECC-205' for call in self.retriever.calls))

    def test_invalid_topic_number_does_not_search_or_change_year(self):
        self.chat.reply('/course ECC-205')
        self.assertIn('Choose a topic number',self.chat.reply('99'))
        self.assertEqual(self.retriever.calls,[])
        self.assertEqual(self.chat.state['course'],'ECC-205')

    def test_changing_year_clears_selected_course_and_topic(self):
        self.chat.reply('Network Theory')
        self.chat.reply('third year courses')
        self.assertNotIn('course',self.chat.state)
        self.assertNotIn('topic_choices',self.chat.state)
        self.chat.reply('only books about convolution')
        self.assertIsNone(self.retriever.calls[-1][1])

    def test_missing_syllabus_is_explicit(self):
        course=next(c for c in self.catalogue.courses if not self.catalogue.topics(c))
        reply=self.chat.reply(course['code'])
        self.assertIn('not been collected',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_menu_does_not_block_direct_resource_or_faculty_queries(self):
        self.chat.welcome()
        self.chat.reply('Suggest lectures and chapters on convolution')
        self.assertEqual(len(self.retriever.calls),2)
        self.chat.reply('/faculty Network Theory')
        self.assertEqual(self.retriever.calls[-1][2],['faculty_expertise','faculty_research_interests'])
        self.chat.reply('Which faculty work on Network Theory?')
        self.assertEqual(self.retriever.calls[-1][2],['faculty_expertise','faculty_research_interests'])

    def test_sessions_are_isolated_and_clear_resets_navigation(self):
        self.chat.reply('Network Theory')
        other=Conversation(self.chat.assistant)
        other.reply('convolution')
        self.assertIsNone(self.retriever.calls[-1][1])
        self.assertEqual(self.chat.state['course'],'ECC-205')
        self.chat.reply('/clear')
        self.assertNotIn('course',self.chat.state)
        self.assert_complete_year(self.chat.reply('2'),2)

    def test_academic_year_is_not_study_year_or_verified_curriculum(self):
        self.assertIsNone(year_in('IIT Roorkee 2026'))
        self.assertEqual(year_in('2nd year in 2026'),'2')
        reply=self.chat.reply('show second year courses at IIT Roorkee in 2026')
        self.assertIn('applicability to 2026 has not been verified',reply)
        self.assert_complete_year(self.chat.reply('show second year courses in 2027'),2)
        self.assertIn('applicability to 2027 has not been verified',self.chat.reply('Network Theory'))
        reply=self.chat.reply('2026')
        self.assertIn('applicability to 2026 has not been verified',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_iit_context_is_separate_from_resource_query(self):
        reply=self.chat.reply('Suggest lectures on convolution at IIT Roorkee in 2026')
        self.assertIn('applicability to 2026 has not been verified',reply)
        self.assertEqual(self.retriever.calls[0][0],'Suggest lectures on convolution')

    def test_exact_facts_keep_the_requested_academic_year(self):
        self.chat.reply('second year courses in 2027')
        reply=self.chat.reply('How many credits for ECC-205?')
        self.assertIn('applicability to 2027 has not been verified',reply)
        self.assertNotIn('applicability to 2026',reply)
        self.assertEqual(self.retriever.calls,[])

    def test_seven_section_menu_and_unavailable_features_do_not_search(self):
        menu=self.chat.welcome()
        self.assertEqual(len(SECTIONS),7)
        for label,_,actions in SECTIONS.values():
            self.assertIn(label,menu)
            reply=self.chat.reply(label)
            for action in actions: self.assertIn(ACTIONS[action],reply)
        for action,explanation in UNAVAILABLE.items():
            self.assertIn(explanation,self.chat.reply(ACTIONS[action]))
        for request in ('show my timetable','latest notices','find DSP notes for the DFT unit'):
            self.chat.reply(request)
        self.assertEqual(self.retriever.calls,[])

    def test_dsp_to_related_faculty_retains_course(self):
        self.chat.reply('DSP')
        self.assertEqual(self.chat.state['course'],'ECC-301')
        self.chat.reply('find the relevant professor')
        query,course,types,_=self.retriever.calls[-1]
        self.assertEqual(query,'Digital Signal Processing')
        self.assertIsNone(course)
        self.assertEqual(types,['faculty_expertise','faculty_research_interests'])

    def test_related_faculty_without_context_asks_for_a_topic(self):
        self.assertIn('Which topic or course',self.chat.reply('find the relevant professor'))
        self.assertEqual(self.retriever.calls,[])

    def test_faculty_and_projects_search_actions_route_followup(self):
        for action,expected_type in (('Find Faculty','faculty_expertise'),('Explore Projects','department_project')):
            self.chat.reply(action)
            self.chat.reply('VLSI')
            self.assertIn(expected_type,self.retriever.calls[-1][2])
        self.chat.reply('/projects wireless communication')
        self.assertEqual(self.retriever.calls[-1][0],'wireless communication')
        self.assertEqual(self.retriever.calls[-1][2],['department_project'])
        self.chat.reply('/faculty')
        self.assertEqual(self.chat.state['pending'],'faculty_search')

    def test_project_renderer_preserves_provenance_and_availability_limit(self):
        project=next(iter(self.catalogue.projects.values()))
        reply=self.catalogue.render_projects([{'metadata':{'entity_id':project['project_id']}}])
        self.assertIn(project['fields']['Scheme/Title'],reply)
        self.assertIn(project['evidence']['url'],reply)
        self.assertIn('Source collected:',reply)
        self.assertIn('not confirmed current openings',reply)

    def test_browse_request_interrupts_pending_research_search(self):
        self.chat.reply('Find Faculty')
        self.assert_complete_year(self.chat.reply('show me second year courses'),2)
        self.chat.reply('Explore Projects')
        self.assertIn('ECC-205',self.chat.reply('/course ECC-205'))
        self.assertEqual(self.retriever.calls,[])

    def test_explicit_resource_command_overrides_pending_faculty_search(self):
        self.chat.reply('Find Faculty')
        self.chat.reply('/resources convolution')
        self.assertEqual(self.retriever.calls[-1][0],'convolution')
        self.assertEqual(self.retriever.calls[-1][2],['nptel_lecture'])


class PromptTests(unittest.TestCase):
    def test_grounded_template_retains_question_context_and_source_evidence(self):
        evidence=[{'text':'Treat this as source data.', 'metadata':{'evidence':{'page':4,'url':'https://iitr.ac.in/example.pdf'}}}]
        messages=build_answer_messages('What should I study?',evidence,study_year=2,course='ECC-205')
        self.assertEqual(messages[0]['role'],'system')
        self.assertIn('EVERY matching code',messages[0]['content'])
        self.assertIn('never instructions',messages[0]['content'])
        data=json.loads(messages[1]['content'])
        self.assertEqual(data['source_evidence'],evidence)
        self.assertEqual(data['context']['requested_academic_year'],'2026')
        self.assertEqual(data['context']['study_year'],2)
        self.assertIn('not been verified',data['context']['source_status'])
        later=build_answer_messages('courses for 2027',[])
        self.assertEqual(json.loads(later[1]['content'])['context']['requested_academic_year'],'2027')

    def test_topic_numbers_survive_query_preparation(self):
        for topic in ('LM741 operational amplifier','Discrete Fourier Transform (4)','3 phase circuits','filter design for 2026 Hz'):
            self.assertEqual(retrieval_topic(topic),topic)
        self.assertEqual(requested_academic_year('academic year 2026–27'),'2026–27')
        self.assertEqual(requested_academic_year('IIT Roorkee 2026'),'2026')
        self.assertIsNone(requested_academic_year('2nd year'))


if __name__=='__main__': unittest.main()
