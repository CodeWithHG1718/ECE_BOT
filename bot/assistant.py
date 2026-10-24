"""Transport-independent study guidance, usable before Telegram setup."""
import re
from html import escape
from bot.catalogue import Catalogue, link
from bot.prompts import retrieval_topic, DEFAULT_ACADEMIC_YEAR
from bot.local_llm import LocalModelError, generation_request


class StudyAssistant:
    def __init__(self, retriever, catalogue=None, llm=None):
        self.retriever = retriever
        self.catalogue = catalogue or Catalogue()
        self.llm = llm
        self.course_prefixes = {m.group(1) for c in self.catalogue.courses
            if (m:=re.fullmatch(r'([A-Z]+)-?\d{3}',c['code']))} | {'ECN'}

    def _compose(self, text, hits, fallback, *, course=None, academic_year=None, history=None, general=False, syllabus=None):
        if self.llm is None or (not hits and not general and not syllabus): return fallback
        context_hits=([syllabus]+hits) if syllabus else hits
        try:
            generated=self.llm.generate(text,context_hits,course=course,academic_year=academic_year,
                                        history=history,mode='overview' if syllabus else 'general' if general else 'grounded')
        except LocalModelError:
            if syllabus:
                fallback=escape(syllabus['text'])+'\n'+link('Related syllabus · '+syllabus['source_code'],syllabus['url'])+'\n\n'+fallback
            return 'The local answer model is unavailable or returned an unusable answer.\n\n'+fallback
        label='Syllabus study guide · local AI' if syllabus else 'General study guidance · local AI' if general else 'Study guidance · local AI'
        source='\n'+link('Related syllabus · '+syllabus['source_code'],syllabus['url']) if syllabus else ''
        return f'<b>{label}</b>\n{generated}'+source+ ('\n\n'+fallback if hits else '')

    def project_reply(self, text, history=None):
        hits=self.retriever.search(retrieval_topic(text),None,['department_project'],8)
        hits=self.catalogue.visible_hits(hits,projects=True)
        # Availability and institutional facts stay in the source renderer.
        return self.catalogue.render_projects(hits)

    def reply(self, text, course=None, faculty=False, academic_year=DEFAULT_ACADEMIC_YEAR, history=None, general=False, search_query=None, syllabus=None):
        if not isinstance(text,str) or not text.strip() or len(text)>1000:
            return 'Send a topic of 1–1,000 characters. Example: convolution or digital circuits.'
        if re.fullmatch(r'(hi|hello|hey|thanks|thank you)[!. ]*',text.strip(),re.I):
            return 'Hello! Send an ECE topic and I’ll suggest where to study it. Try “convolution”, use /courses to browse by year, or /faculty VLSI for research profiles.'
        explicit = next((c['code'] for c in self.catalogue.courses if re.search(
            r'(?<![A-Z0-9])'+re.escape(c['code']).replace(r'\-','-?')+r'(?![A-Z0-9])',text.upper())),None)
        if not explicit and re.search(r'\b(?:'+'|'.join(sorted(self.course_prefixes))+r')-?\d{3}\b',text.upper()):
            return 'That course code isn’t in the supplied curriculum. Please choose a code from /courses; I won’t substitute a similarly numbered syllabus course.'
        course = explicit or course
        if re.search(r'\b(credits?|semester|course code)\b',text,re.I):
            code = course
            found = self.catalogue.course(code) if code else None
            return self.catalogue.course_details(found,academic_year) if found else 'Please specify a curriculum code, such as ECC-106, so I can give the correct credits and semester. Use /courses to find it.'
        faculty = faculty or bool(re.search(r'\b(faculty|professor|researcher|mentor|supervisor)\b',text,re.I))
        search_text = retrieval_topic(search_query or text)
        if faculty:
            hits = self.retriever.search(search_text,None,['faculty_expertise','faculty_research_interests'],12)
        else:
            only_lectures = bool(re.search(r'\bonly\s+(?:lectures?|videos?)\b',text,re.I))
            only_books = bool(re.search(r'\bonly\s+(?:books?|chapters?)\b',text,re.I))
            hits = []
            if not only_lectures: hits += self.retriever.search(search_text,course,['book_chapter'],2)
            if not only_books: hits += self.retriever.search(search_text,course,['nptel_lecture'],2)
        hits = self.catalogue.visible_hits(hits,faculty=faculty)
        answer = self.catalogue.render_hits(hits,faculty)
        if not faculty:
            answer = self._compose(text,hits,answer,course=course,academic_year=academic_year,history=history,
                                   general=general or generation_request(text),syllabus=syllabus)
        return f'<b>Searching {escape(course)}</b> · /clear to reset\n\n'+answer if course and not faculty else answer
