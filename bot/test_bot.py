"""Exercise Telegram handler logic with mocks; never contacts Telegram."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from bot.catalogue import Catalogue
from bot.main import make_application, year_keyboard
from bot.navigation import SECTIONS


class FakeRetriever:
    def __init__(self): self.calls=[]; self.fail=False
    def search(self,*args):
        self.calls.append(args)
        if self.fail: raise RuntimeError('model offline')
        return [{'metadata':{'entity_id':'oppenheim-signals-2:chapter:2'}}]


class BotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.retriever=FakeRetriever()
        self.app=make_application('123456:local-test-token-not-a-real-credential',Catalogue(),self.retriever)
        self.context=SimpleNamespace(args=[],user_data={},bot=SimpleNamespace(send_chat_action=AsyncMock()))

    def update(self,text='/start',callback=None):
        message=SimpleNamespace(text=text,reply_text=AsyncMock())
        return SimpleNamespace(effective_message=message,effective_chat=SimpleNamespace(type='private',id=1),
            callback_query=SimpleNamespace(data=callback,answer=AsyncMock()))

    def command(self,name):
        return next(h.callback for h in self.app.handlers[0] if name in getattr(h,'commands',()))

    async def test_start_and_year_menu(self):
        update=self.update()
        await self.command('start')(update,self.context)
        self.assertIn('Signal',update.effective_message.reply_text.call_args.args[0])
        keyboard=year_keyboard().inline_keyboard
        self.assertEqual(sum(len(row) for row in keyboard),5)

    async def test_year_callback_shows_complete_semesters_and_course_buttons(self):
        update=self.update(callback='year:2:0')
        handler=next(h.callback for h in self.app.handlers[0] if type(h).__name__=='CallbackQueryHandler')
        await handler(update,self.context)
        update.callback_query.answer.assert_awaited_once()
        args=update.effective_message.reply_text.call_args
        full='\n'.join(call.args[0] for call in update.effective_message.reply_text.call_args_list)
        self.assertIn('Year 2',full)
        self.assertIn('Semester 3',full); self.assertIn('Semester 4',full)
        buttons=args.kwargs['reply_markup'].inline_keyboard
        for course in Catalogue().year_courses('2'):
            self.assertIn(course['code']+' — ',full)
            self.assertTrue(any(b.callback_data=='course:'+course['code'] for row in buttons for b in row))

    async def test_course_filter_clear_and_user_isolation(self):
        self.context.args=['ECC-106']
        await self.command('course')(self.update('/course ECC-106'),self.context)
        self.assertEqual(self.context.user_data['course'],'ECC-106')
        other=SimpleNamespace(args=[],user_data={},bot=self.context.bot)
        await self.command('ask')(self.update('convolution'),other)
        self.assertIsNone(self.retriever.calls[-1][1])
        await self.command('ask')(self.update('convolution'),self.context)
        self.assertEqual(self.retriever.calls[-1][1],'ECC-106')
        await self.command('clear')(self.update('/clear'),self.context)
        self.assertNotIn('course',self.context.user_data)

    async def test_exact_facts_bypass_semantic_search(self):
        update=self.update('How many credits for ECC-203?')
        await self.command('ask')(update,self.context)
        self.assertIn('Electromagnetics',update.effective_message.reply_text.call_args.args[0])
        self.assertEqual(self.retriever.calls,[])

    async def test_model_failure_is_explicit(self):
        self.retriever.fail=True
        update=self.update('convolution')
        await self.command('ask')(update,self.context)
        self.assertIn('unavailable',update.effective_message.reply_text.call_args.args[0])

    async def test_long_queries_do_not_reach_model(self):
        update=self.update('x'*1001)
        await self.command('ask')(update,self.context)
        self.assertEqual(self.retriever.calls,[])

    async def test_greetings_and_unspecified_facts_do_not_guess(self):
        for text in ('hi','How many credits?'):
            await self.command('ask')(self.update(text),self.context)
        self.assertEqual(self.retriever.calls,[])

    async def test_explicit_code_overrides_the_previous_filter(self):
        self.context.user_data['course']='ECC-106'
        update=self.update('Study antennas for ECC-203')
        await self.command('ask')(update,self.context)
        self.assertTrue(all(call[1]=='ECC-203' for call in self.retriever.calls))
        self.assertIn('Searching ECC-203',update.effective_message.reply_text.call_args.args[0])

    async def test_legacy_code_does_not_silently_use_selected_course(self):
        self.context.user_data['course']='ECC-106'
        update=self.update('What are the credits for ECN-203?')
        await self.command('ask')(update,self.context)
        self.assertIn('isn’t in the supplied curriculum',update.effective_message.reply_text.call_args.args[0])
        self.assertEqual(self.retriever.calls,[])

    async def test_component_numbers_are_not_mistaken_for_curriculum_codes(self):
        await self.command('ask')(self.update('LM741 operational amplifier'),self.context)
        self.assertTrue(self.retriever.calls)

    async def test_only_books_request_is_respected(self):
        await self.command('ask')(self.update('only books about convolution'),self.context)
        self.assertEqual(len(self.retriever.calls),1)
        self.assertEqual(self.retriever.calls[0][2],['book_chapter'])

    async def test_natural_year_course_topic_sequence(self):
        handler=self.command('ask')
        update=self.update('show me courses of 2nd year at IIT Roorkee in 2026')
        await handler(update,self.context)
        self.assertEqual(self.retriever.calls,[])
        full='\n'.join(call.args[0] for call in update.effective_message.reply_text.call_args_list)
        for course in Catalogue().year_courses('2'): self.assertIn(course['code']+' — ',full)
        await handler(self.update('Network Theory'),self.context)
        self.assertEqual(self.context.user_data['pending'],'topic')
        await handler(self.update('1'),self.context)
        self.assertEqual(self.retriever.calls[-1][1],'ECC-205')
        self.assertNotEqual(self.retriever.calls[-1][0],'1')

    async def test_complete_long_course_lists_are_split_without_loss(self):
        self.context.args=['all']
        update=self.update('/courses all')
        await self.command('courses')(update,self.context)
        chunks=[call.args[0] for call in update.effective_message.reply_text.call_args_list]
        self.assertGreater(len(chunks),1)
        self.assertTrue(all(len(chunk)<=3500 for chunk in chunks))
        full='\n'.join(chunks)
        for year in ('1','2','3','4'):
            for course in Catalogue().year_courses(year): self.assertIn(course['code']+' — ',full)

    async def test_persistent_menu_and_contextual_section_actions(self):
        update=self.update('/menu')
        await self.command('menu')(update,self.context)
        markup=update.effective_message.reply_text.call_args.kwargs['reply_markup']
        self.assertTrue(markup.is_persistent)
        labels=[button.text for row in markup.keyboard for button in row]
        for label,_,_ in SECTIONS.values(): self.assertIn(label,labels)
        update=self.update('Academics')
        await self.command('ask')(update,self.context)
        markup=update.effective_message.reply_text.call_args.kwargs['reply_markup']
        self.assertIn('action:courses',[b.callback_data for row in markup.inline_keyboard for b in row])
        self.assertEqual(self.retriever.calls,[])

    async def test_related_faculty_action_uses_selected_course(self):
        self.context.user_data['course']='ECC-301'
        update=self.update(callback='action:related_faculty')
        handler=next(h.callback for h in self.app.handlers[0] if type(h).__name__=='CallbackQueryHandler')
        await handler(update,self.context)
        self.assertEqual(self.retriever.calls[-1][0],'Digital Signal Processing')
        self.assertEqual(self.retriever.calls[-1][2],['faculty_expertise','faculty_research_interests'])

    async def test_projects_command_routes_to_project_records(self):
        self.context.args=['VLSI']
        await self.command('projects')(self.update('/projects VLSI'),self.context)
        self.assertEqual(self.retriever.calls[-1][0],'VLSI')
        self.assertEqual(self.retriever.calls[-1][2],['department_project'])

    async def test_faculty_command_without_topic_prompts_instead_of_searching(self):
        await self.command('faculty')(self.update('/faculty'),self.context)
        self.assertEqual(self.context.user_data['pending'],'faculty_search')
        self.assertEqual(self.retriever.calls,[])


if __name__=='__main__': unittest.main()
