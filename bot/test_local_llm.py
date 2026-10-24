"""Local generation contracts, fallbacks and context isolation; no live service needed."""
import json
import unittest
from unittest.mock import patch

from bot.assistant import StudyAssistant
from bot.catalogue import Catalogue
from bot.conversation import Conversation
from bot.local_llm import OllamaChat, LocalModelError, configured_llm


HITS=[{'text':'Chapter 2: Linear Time-Invariant Systems. Convolution.',
       'metadata':{'entity_id':'oppenheim-signals-2:chapter:2','document_type':'book_chapter'}}]


def response(answer='Convolution describes how a system combines an input with its impulse response.',ids=None):
    return {'done':True,'done_reason':'stop','message':{'content':json.dumps(
        {'answer':answer,'source_ids':['S1'] if ids is None else ids})},'eval_count':35}


class StubRetriever:
    def __init__(self,hits=None): self.hits=HITS if hits is None else hits; self.calls=[]
    def search(self,*args): self.calls.append(args); return self.hits


class LocalLlmTests(unittest.TestCase):
    def setUp(self): self.llm=OllamaChat()

    def test_endpoint_is_local_only_and_generation_can_be_disabled(self):
        for endpoint in ('https://api.example.com','http://10.0.0.1:11434',
                         'http://user:secret@localhost:11434','http://localhost:11434/proxy'):
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError): OllamaChat(endpoint)
        with patch.dict('os.environ',{'SIGNAL_LLM':'off'}): self.assertIsNone(configured_llm())

    def test_request_is_bounded_and_uses_validated_local_model(self):
        with patch.object(self.llm,'_request',return_value=response()) as send:
            self.llm.generate('convolution',HITS)
        path,body=send.call_args.args
        self.assertEqual(path,'/api/chat')
        self.assertEqual(body['model'],'qwen3:4b-instruct')
        self.assertFalse(body['stream'])
        self.assertEqual(body['options']['num_ctx'],4096)
        self.assertLessEqual(body['options']['num_predict'],600)
        data=json.loads(body['messages'][1]['content'])
        self.assertEqual(data['source_evidence'][0]['id'],'S1')
        self.assertEqual(data['context']['institute'],'IIT Roorkee')

    def test_evidence_is_deduplicated_and_bounded(self):
        hits=[{'text':'x'*2000,'metadata':{'entity_id':str(n)}} for n in range(10)]
        records=self.llm.evidence([hits[0]]+hits)
        self.assertEqual(len(records),4)
        self.assertTrue(all(len(r['text'])<=1100 for r in records))

    def test_invented_links_invalid_ids_and_truncated_json_are_rejected(self):
        bad=[response('Visit https://fake.example'), response(ids=['S99']),response(ids=[]),
             {'done':True,'done_reason':'length','message':{'content':'{}'}},
             {'done':True,'message':{'content':'not json'}},response(answer='')]
        for value in bad:
            with self.subTest(value=value),patch.object(self.llm,'_request',return_value=value),self.assertRaises(LocalModelError):
                self.llm.generate('convolution',HITS)

    def test_html_is_escaped_and_successful_answers_are_cached(self):
        with patch.object(self.llm,'_request',return_value=response('x < y & z')) as send:
            first=self.llm.generate('convolution',HITS)
            self.assertEqual(first,'x &lt; y &amp; z')
            self.assertEqual(self.llm.generate('convolution',HITS),first)
            send.assert_called_once()
            self.assertTrue(self.llm.last_stats['cached'])

    def test_cache_separates_history_and_is_bounded(self):
        with patch.object(self.llm,'_request',return_value=response()) as send:
            for n in range(34): self.llm.generate('convolution',HITS,history=[{'question':str(n),'answer':'context'}],mode='general')
        self.assertEqual(send.call_count,34)
        self.assertEqual(len(self.llm.cache),32)

    def test_empty_evidence_cannot_produce_a_grounded_claim(self):
        with patch.object(self.llm,'_request') as send,self.assertRaises(LocalModelError):
            self.llm.generate('2026 faculty teaching assignments',[])
        send.assert_not_called()
        with patch.object(self.llm,'_request',return_value=response(ids=[])):
            self.assertTrue(self.llm.generate('Explain convolution',[],mode='general'))

    def test_only_displayed_sources_reach_generation(self):
        catalogue=Catalogue()
        hits=[{'text':'Book source','metadata':{'entity_id':entity}}
              for entity in list(catalogue.books)[:7]]
        assistant=StudyAssistant(StubRetriever(hits),catalogue,llm=self.llm)
        with patch.object(self.llm,'generate',return_value='A study resource.') as generate:
            assistant.reply('convolution')
            self.assertEqual(len(generate.call_args.args[1]),2)

    def test_institutional_faculty_and_project_facts_bypass_generation(self):
        assistant=StudyAssistant(StubRetriever(),llm=self.llm)
        with patch.object(self.llm,'generate') as generate:
            assistant.reply('VLSI',faculty=True)
            assistant.project_reply('VLSI')
        generate.assert_not_called()

    def test_changing_courses_clears_old_generation_context(self):
        chat=Conversation(StudyAssistant(StubRetriever(),llm=self.llm))
        with patch.object(self.llm,'generate',return_value='Explanation.'):
            chat.reply('Explain convolution')
        chat.reply('DSP')
        self.assertNotIn('history',chat.state)
        self.assertNotIn('last_topic',chat.state)

    def test_unavailable_model_keeps_verified_links(self):
        assistant=StudyAssistant(StubRetriever(),llm=self.llm)
        with patch.object(self.llm,'generate',side_effect=LocalModelError('timeout')):
            reply=assistant.reply('convolution')
        self.assertIn('local answer model is unavailable',reply)
        self.assertIn('<a href=',reply)
        self.assertIn('Linear Time-Invariant Systems',reply)

    def test_exact_course_navigation_and_missing_data_never_call_llm(self):
        chat=Conversation(StudyAssistant(StubRetriever(),llm=self.llm))
        with patch.object(self.llm,'generate') as generate:
            for query in ('second year courses','ECC-205','How many credits for ECC-205?',
                          'show my timetable','latest notices','find DSP notes'):
                chat.reply(query)
        generate.assert_not_called()
        self.assertIn('Highlights:',chat.reply('what are the main topics in 2nd year of ECE?'))

    def test_explanations_use_selected_unit_then_followup_history(self):
        chat=Conversation(StudyAssistant(StubRetriever(),llm=self.llm))
        chat.reply('DSP')
        with patch.object(self.llm,'generate',return_value='A sample explanation.') as generate:
            answer=chat.reply('Explain the second unit')
            self.assertIn('Syllabus study guide',answer)
            self.assertEqual(generate.call_args.kwargs['mode'],'overview')
            self.assertEqual(generate.call_args.args[1][0]['metadata']['document_type'],'syllabus_topic')
            self.assertIn('Sampling and Quantization',generate.call_args.args[0])
            self.assertEqual(generate.call_args.kwargs['course'],'ECC-301')
            self.assertEqual(chat.assistant.retriever.calls[-1][0],'Sampling and Quantization')
            chat.reply('make it simpler with an example')
            self.assertIn('Sampling and Quantization',generate.call_args.args[0])
            self.assertTrue(generate.call_args.kwargs['history'])
            self.assertEqual(chat.assistant.retriever.calls[-1][0],'Sampling and Quantization')
            self.assertEqual(len(chat.state['history']),2)

    def test_history_is_per_user_and_clear_removes_it(self):
        assistant=StudyAssistant(StubRetriever(),llm=self.llm)
        one=Conversation(assistant); two=Conversation(assistant)
        with patch.object(self.llm,'generate',return_value='Explanation.') as generate:
            one.reply('Explain convolution')
            two.reply('Explain modulation')
            self.assertIsNone(generate.call_args.kwargs['history'])
        one.reply('/clear')
        self.assertNotIn('history',one.state)

    def test_enabled_menu_actions_generate_general_guidance(self):
        for action in ('Explain a Topic','Study Planner','Skill Roadmaps','Interview Prep'):
            chat=Conversation(StudyAssistant(StubRetriever(),llm=self.llm))
            chat.reply(action)
            self.assertEqual(chat.state['pending'],'generation')
            with patch.object(self.llm,'generate',return_value='Study advice.') as generate:
                chat.reply('convolution, beginner, three days')
                self.assertEqual(generate.call_args.kwargs['mode'],'general')


if __name__=='__main__': unittest.main()
