"""Run: .venv-embeddings/Scripts/python.exe -m bot.main"""
import argparse
import asyncio
import logging
import os
import re
from time import monotonic

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from bot.catalogue import Catalogue, ROOT
from bot.assistant import StudyAssistant
from bot.conversation import Conversation
from bot.navigation import SECTIONS, ACTIONS
from bot.local_llm import configured_llm
from ingestion.bge_embeddings import Retriever

def token_from_environment():
    token = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token and (ROOT/'.env').exists():
        for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('TELEGRAM_BOT_TOKEN='):
                token = line.split('=',1)[1].strip().strip('\"\'')
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token):
        raise ValueError('Set TELEGRAM_BOT_TOKEN in the project .env file or environment. Create it through @BotFather. Never put it in source code.')
    return token


def year_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f'Year {y}',callback_data=f'year:{y}:0') for y in (1,2)],
        [InlineKeyboardButton(f'Year {y}',callback_data=f'year:{y}:0') for y in (3,4)],
        [InlineKeyboardButton('Electives & additional options',callback_data='year:options:0')]])


def main_keyboard():
    labels=[s[0] for s in SECTIONS.values()]
    return ReplyKeyboardMarkup([labels[i:i+2] for i in range(0,len(labels),2)]+[['Main Menu']],
                               resize_keyboard=True,is_persistent=True)


def contextual_keyboard(state):
    if state.get('pending')=='menu': return main_keyboard()
    if state.get('pending')=='year': return year_keyboard()
    if state.get('pending')=='section' and state.get('section') in SECTIONS:
        actions=SECTIONS[state['section']][2]
    elif state.get('course') and state.get('pending') not in ('faculty_search','project_search'):
        actions=('topics','resources','related_faculty')
    elif state.get('section') in SECTIONS:
        actions=SECTIONS[state['section']][2]
    else: actions=()
    buttons=[InlineKeyboardButton(ACTIONS[key],callback_data='action:'+key) for key in actions]
    rows=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    rows.append([InlineKeyboardButton('Main Menu',callback_data='menu')])
    return InlineKeyboardMarkup(rows)


def make_application(token, catalogue, retriever, llm=None):
    search_lock = asyncio.Lock()
    assistant = StudyAssistant(retriever,catalogue,llm=llm)

    async def respond(update, text, keyboard=None):
        # Complete course/topic lists can exceed Telegram's single-message limit.
        chunks=[]; current=''
        for line in text.splitlines():
            if current and len(current)+len(line)+1>3500:
                chunks.append(current); current=''
            current+=('\n' if current else '')+line
        if current: chunks.append(current)
        for i,chunk in enumerate(chunks):
            await update.effective_message.reply_text(chunk,parse_mode=ParseMode.HTML,
                reply_markup=keyboard if i==len(chunks)-1 else None,disable_web_page_preview=True)

    async def private(update):
        if update.effective_chat and update.effective_chat.type=='private': return True
        if update.effective_message:
            await respond(update,'Please open a private chat with Signal to use the study companion.')
        return False

    async def start(update, context):
        if await private(update): await respond(update,Conversation(assistant,context.user_data).welcome(),main_keyboard())

    async def courses(update, context):
        if await private(update):
            await respond(update,Conversation(assistant,context.user_data).reply('/courses '+' '.join(context.args)),year_keyboard())

    async def clear(update, context):
        if await private(update):
            await respond(update,Conversation(assistant,context.user_data).reply('/clear'),main_keyboard())

    async def select_course(update, context, code):
        course = catalogue.course(code)
        if course is None:
            return await respond(update,'I couldn’t find that curriculum code. Use /courses to browse, or try /course ECC-106.')
        await respond(update,Conversation(assistant,context.user_data).choose_course(course),contextual_keyboard(context.user_data))

    async def course_command(update, context):
        if await private(update): await select_course(update,context,' '.join(context.args))

    async def callback(update, context):
        await update.callback_query.answer()
        if not await private(update): return
        value = update.callback_query.data or ''
        if value=='menu': return await start(update,context)
        if value.startswith('action:'):
            action=value.partition(':')[2]
            if action in ACTIONS: return await query(update,context,text_override=ACTIONS[action])
            return
        if value=='years': return await courses(update,context)
        if value.startswith('course:'):
            return await select_course(update,context,value.split(':',1)[1])
        match = re.fullmatch(r'year:(1|2|3|4|options):(\d{1,3})',value)
        if not match: return
        year = match.group(1)
        rows = catalogue.year_courses(year)
        text = Conversation(assistant,context.user_data).choose_year(year)
        buttons = [[InlineKeyboardButton(c['code']+' · '+c['title'][:32],callback_data='course:'+c['code'])] for c in rows]
        buttons.append([InlineKeyboardButton('Choose another year',callback_data='years')])
        await respond(update,text,InlineKeyboardMarkup(buttons))

    async def query(update, context, faculty=False, text_override=None):
        if not await private(update): return
        text = text_override if text_override is not None else update.effective_message.text
        if text.startswith('/'):
            command=text.split()[0].split('@')[0]
            args=' '.join(context.args or []) if text_override is None else text.partition(' ')[2]
            text=args if (faculty and args) or (command=='/ask' and args) else command+(' '+args if args else '')
        if not text or not text.strip() or len(text)>1000:
            return await respond(update,'Send a topic of 1–1,000 characters. Example: convolution, digital circuits, or /faculty VLSI.')
        conversation=Conversation(assistant,context.user_data)
        structured=conversation.structured_reply(text) if not faculty or text=='/faculty' else None
        if structured is not None: return await respond(update,structured,contextual_keyboard(context.user_data))
        # Fast structured replies do not need the semantic-search queue.
        if re.fullmatch(r'(hi|hello|hey|thanks|thank you)[!. ]*',text.strip(),re.I) or re.search(r'\b(credits?|semester|course code)\b',text,re.I):
            return await respond(update,conversation.reply(text,faculty))
        now = monotonic()
        if search_lock.locked() or now-context.user_data.get('last_query',0)<2:
            return await respond(update,'I’m finishing a search. Please try again in a moment.')
        context.user_data['last_query'] = now
        faculty = faculty or bool(re.search(r'\b(faculty|professor|researcher|mentor|supervisor)\b',text,re.I))
        async with search_lock:
            await context.bot.send_chat_action(update.effective_chat.id,ChatAction.TYPING)
            try:
                answer = await asyncio.to_thread(conversation.reply,text,faculty)
            except Exception:
                return await respond(update,'The local search model is unavailable right now. Please try again shortly. Course browsing with /courses still works.')
        await respond(update,answer,contextual_keyboard(context.user_data))

    async def faculty_command(update, context): await query(update,context,faculty=True)

    async def unknown(update, context):
        if await private(update): await respond(update,'Use /help to see the available commands, or send an ECE study topic.')

    async def on_error(update, context):
        # Never log HTTP request URLs (which contain the Telegram bot token) or message bodies.
        logging.getLogger('signal').error('Bot request failed: %s',type(context.error).__name__)

    async def post_init(app):
        await app.bot.set_my_commands([BotCommand(c,d) for c,d in [
            ('start','Meet ECE Companion'),('menu','Main catalogue'),('courses','Browse courses by year'),
            ('course','Select a course code'),('faculty','Find faculty research'),
            ('projects','Explore recorded research projects'),('resources','Find course resources'),
            ('timetable','Timetable availability'),('notices','Notices availability'),('search','Search the collected catalogue'),
            ('clear','Clear course filter'),('help','How to use Signal')]])

    app = Application.builder().token(token).concurrent_updates(4).post_init(post_init).build()
    for names, handler in [(['start','help','menu'],start),(['courses'],courses),(['course'],course_command),
                           (['clear'],clear),(['faculty'],faculty_command),
                           (['ask','projects','resources','search','timetable','notices'],query)]:
        app.add_handler(CommandHandler(names,handler))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,query))
    app.add_handler(MessageHandler(filters.COMMAND,unknown))
    app.add_error_handler(on_error)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',help='Run a real local search without connecting to Telegram')
    parser.add_argument('--course',help='Course filter for --demo')
    args = parser.parse_args()
    catalogue = Catalogue()
    if args.demo:
        from bot.local_chat import LazyRetriever
        print(Conversation(StudyAssistant(LazyRetriever(),catalogue,llm=configured_llm()),{'course':args.course}).reply(args.demo))
        return
    try: token = token_from_environment()
    except ValueError as exc: parser.exit(2,str(exc)+'\n')
    logging.basicConfig(level=logging.WARNING,format='%(levelname)s: %(message)s')
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    logging.getLogger('httpcore').setLevel(logging.CRITICAL)
    app = make_application(token,catalogue,Retriever(),llm=configured_llm())
    print('Signal is starting Telegram long polling. Keep this laptop awake. Ctrl+C stops the bot.',flush=True)
    app.run_polling(allowed_updates=['message','callback_query'],drop_pending_updates=False)


if __name__=='__main__': main()
