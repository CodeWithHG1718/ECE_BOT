"""Structured conversational navigation shared by local and Telegram adapters.

Session state is caller-owned so users never share a year, course or topic choice.
"""
from html import escape
import re
from bot.catalogue import link, topic_query
from bot.prompts import academic_note, requested_academic_year, DEFAULT_ACADEMIC_YEAR
from bot.navigation import SECTIONS, ACTIONS, UNAVAILABLE, main_menu, section_menu
from bot.local_llm import generation_request, casual_conversation_request

WELCOME = main_menu()
YEAR_PROMPT = 'Which year? Reply 1, 2, 3, or 4. For unassigned electives, type “options”.'
YEAR_WORDS={'1':'1','1st':'1','first':'1','one':'1','2':'2','2nd':'2','second':'2','two':'2',
            '3':'3','3rd':'3','third':'3','three':'3','4':'4','4th':'4','fourth':'4','four':'4','final':'4'}


def year_in(text):
    values='|'.join(sorted(YEAR_WORDS,key=len,reverse=True))
    match=re.search(r'\b('+values+r')[-\s]*(?:year|yr)\b|\b(?:year|yr)\s*('+values+r')\b',text,re.I)
    return YEAR_WORDS[(match.group(1) or match.group(2)).lower()] if match else None


class Conversation:
    def __init__(self, assistant, state=None):
        self.assistant=assistant
        self.catalogue=assistant.catalogue
        self.state=state if state is not None else {}

    def welcome(self):
        self.state['pending']='menu'
        self.state.pop('section',None)
        for key in ('timetable_year','timetable_section','timetable_batch','timetable_course','timetable_day','timetable_personal','timetable_student_batch'):
            self.state.pop(key,None)
        return WELCOME

    def section(self, key):
        self.state.update(section=key,pending='section')
        return section_menu(key)

    def action(self, key):
        if key=='timetable':
            for name in ('timetable_year','timetable_section','timetable_batch','timetable_course','timetable_day','timetable_student_batch'):
                self.state.pop(name,None)
            self.state.update(pending='timetable_year',timetable_personal=True)
            return ('Which study year is your timetable for? Reply 1, 2, 3, or 4. '
                    'I’ll ask for your student section when the source contains section labels.')
        if key in ('explain','planner','roadmaps','interviews') and self.assistant.llm is not None:
            self.state.update(pending='generation',generation_intent=key)
            prompts={
                'explain':'Which ECE topic should I explain? You can also select a course, then ask “Explain the second unit”.',
                'planner':'What topic or course are you studying, and how much time do you have?',
                'roadmaps':'Which ECE skill do you want to learn, and what do you already know?',
                'interviews':'Which ECE area should the practice questions cover? Tell me your experience level.',
            }
            return prompts[key]
        if key in UNAVAILABLE:
            self.state['pending']=None
            return UNAVAILABLE[key]+'\n\nType “menu” to choose another section.'
        if key=='courses':
            self.state['pending']='year'
            return YEAR_PROMPT
        if key in ('faculty','research','projects'):
            self.state['pending']='project_search' if key=='projects' else 'faculty_search'
            return 'Which research topic interests you? For example: VLSI, signal processing, or wireless communication.'
        if key in ('topics','related_faculty') and not self.state.get('course'):
            self.state['pending']='year'
            return 'Choose a course first. '+YEAR_PROMPT
        if key=='topics': return self.choose_course(self.catalogue.course(self.state['course']))
        if key=='related_faculty': return None  # Resolve through reply() and the search queue.
        if key in ('resources','search'):
            self.state['pending']='resource_search'
            selected=self.state.get('course')
            return ('Tell me a topic'+(f' for {selected}' if selected else '')+'. Example: convolution or DFT.'
                    '\nI can find books, lectures, faculty and recorded research projects in the collected catalogue.')
        return 'Type “menu” to see the available sections.'

    def choose_year(self, year, topics=False):
        for key in ('timetable_year','timetable_section','timetable_batch','timetable_course','timetable_day','timetable_personal'):
            self.state.pop(key,None)
        self.state.update(year=year,pending='course')
        self.state.pop('course',None)
        self.state.pop('topic_choices',None)
        self.state.pop('history',None)
        self.state.pop('last_topic',None)
        self.state.pop('search_topic',None)
        self.state.pop('syllabus_context',None)
        return self.catalogue.year_overview(year,topics,self.state.get('academic_year',DEFAULT_ACADEMIC_YEAR))

    def choose_course(self, course):
        if self.state.get('course')!=course['code']:
            self.state.pop('history',None)
            self.state.pop('last_topic',None)
            self.state.pop('search_topic',None)
            self.state.pop('syllabus_context',None)
        self.state.update(course=course['code'],pending='topic')
        units=self.catalogue.topics(course)
        self.state['topic_choices']=[s['text'] for s,_ in units]
        lines=[self.catalogue.course_details(course,self.state.get('academic_year',DEFAULT_ACADEMIC_YEAR)).split('\n\nUse this course')[0], '', '<b>Topics to study</b>']
        if not units:
            lines += ['Detailed syllabus topics have not been collected for this course yet.',
                      'Tell me a specific topic to look for related books and lectures, or choose another course.']
            self.state['pending']=None
        else:
            for i,(section,syllabus) in enumerate(units,1):
                status=self.catalogue.topic_resource_status(course['code'],i)
                suffix=f' · {escape(status)}' if status else ''
                lines.append(f"{i}. {escape(section['text'])}{suffix}")
            for sid in dict.fromkeys(s['syllabus_id'] for _,s in units):
                syllabus=self.catalogue.syllabi[sid]
                lines.append(link(f"Related syllabus: {syllabus['source_code']}",
                    f"https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_syll_22.pdf#page={syllabus['pages'][0]}"))
            book_count=self.catalogue.course_book_reference_count(course['code'])
            if book_count:
                lines.append(f'Linked syllabus reading list: {book_count} book recommendations. Ask “which books should I read?” to see them.')
            lines += ['', 'A starting point is the first listed unit above (syllabus order, not an official prerequisite sequence).',
                      'Which topic would you like resources for? Reply with its number or name.']
        return '\n'.join(lines)

    def timetable_reply(self, text, *, personal=False):
        timetable=self.catalogue.timetable
        continuing=self.state.get('pending') in ('timetable_year','timetable_section')
        personal=personal or bool(re.search(r'\bmy\b',text,re.I)) or (continuing and self.state.get('timetable_personal',False))
        year=year_in(text)
        section=timetable.match_section(text)
        if not section:
            unknown_section=re.search(r'\b\d{2}EC\d{1,2}\b',text,re.I)
            section=unknown_section.group(0).upper() if unknown_section else None
        student_batch_in_text=timetable.match_student_batch_number(text)
        student_batch=student_batch_in_text
        if student_batch is None:
            student_batch=self.state.get('timetable_student_batch')
        if not section and student_batch is not None:
            section=timetable.resolve_student_batch(student_batch,year)
        if section:
            self.state.pop('timetable_student_batch',None)
        elif student_batch is not None:
            self.state['timetable_student_batch']=student_batch
        batch=timetable.match_batch(text)
        if student_batch_in_text is not None and not re.search(r'\b(?:course|timetable)\s+batch\b',text,re.I):
            batch=None
        course=timetable.match_course(text)
        day=timetable.match_day(text)
        if not year and re.fullmatch(r'\s*[1-4]\s*',text) and not batch:
            year=text.strip()
        explicit_year=year
        if explicit_year and self.state.get('timetable_year') not in (None,explicit_year):
            for key in ('timetable_section','timetable_batch','timetable_course','timetable_day','timetable_student_batch'):
                self.state.pop(key,None)
        if not year:
            year=self.state.get('timetable_year')
        if not year and section:
            year=timetable.year_for_section(section)
        if not year and course:
            candidates=timetable.years_for_course(course)
            if len(candidates)==1: year=candidates[0]
            elif len(candidates)>1:
                self.state.update(pending='timetable_year',timetable_personal=personal,timetable_course=course)
                return f'{course} appears in more than one year. Which year should I show: '+', '.join(candidates)+'?'
        if not year:
            self.state.update(pending='timetable_year',timetable_personal=personal)
            return 'Which study year should I show? Reply 1, 2, 3, or 4.'

        self.state['timetable_year']=year
        if section: self.state['timetable_section']=section
        if batch is not None: self.state['timetable_batch']=batch
        if course: self.state['timetable_course']=course
        if day: self.state['timetable_day']=day
        section=self.state.get('timetable_section')
        batch=self.state.get('timetable_batch')
        course=self.state.get('timetable_course')
        day=self.state.get('timetable_day')
        available=timetable.sections(year)
        if section and section not in available:
            self.state.update(pending='timetable_section',timetable_personal=personal)
            if available:
                return f'{section} is not listed under Year {year}. Choose a section from: '+', '.join(available)+'.'
            return (f'Year {year} has no student-section labels in this extract, so I can’t confirm '
                    f'a personalized schedule for {section}. Type “all” to inspect the year-wide OCR rows.')
        if personal and not section and available and text.strip().casefold()!='all':
            self.state.update(pending='timetable_section',timetable_personal=True)
            return (f'Which student section? The extract lists: {", ".join(available)}. '
                    'Reply with one label, such as 25EC1. A timetable batch label is a separate field.')
        result=timetable.render(year,section=section,batch=batch,course_code=course,day=day,
                                course_title=self.catalogue.course_title)
        if personal and not available:
            result=('This year has no student-section labels in the extracted source, so these rows '
                    'cannot be confirmed as your personalized timetable.\n\n'+result)
        if re.search(r'\b(today|tomorrow|next class|right now|currently)\b',text,re.I):
            result=('The extract has no dated occurrences, holiday calendar, or change notices; '
                    'I can show recurring weekday slots but cannot confirm the next calendar class.\n\n'+result)
        self.state['pending']=None
        return result

    def structured_reply(self, text):
        if not isinstance(text,str) or not text.strip() or len(text)>1000:
            return 'Please send a question of 1–1,000 characters.'
        text=text.strip(); lower=text.lower()
        academic_year=requested_academic_year(text)
        if academic_year: self.state['academic_year']=academic_year
        if lower in ('menu','main menu','/menu','help','/help','/start','hi','hello','hey'):
            return self.welcome()
        if lower=='back':
            return self.section(self.state['section']) if self.state.get('section') else self.welcome()
        section=next((key for key,(label,_,_) in SECTIONS.items() if lower==label.lower()),None)
        if section: return self.section(section)
        action=next((key for key,label in ACTIONS.items() if lower==label.lower()),None)
        if lower.startswith('/timetable'):
            argument=text.partition(' ')[2].strip()
            return self.timetable_reply(argument or 'my timetable',personal=True)
        commands={'/timetable':'timetable','/notices':'notices','/projects':'projects',
                  '/resources':'resources','/search':'search','/faculty':'faculty'}
        if action or lower in commands: return self.action(action or commands[lower])
        if lower in ('/clear','clear','reset','start over'):
            self.state.clear()
            return 'Your selections are cleared.\n\n'+self.welcome()
        if lower.startswith('/courses'):
            value=lower.partition(' ')[2].strip()
            if value in ('all','1-4','1–4'):
                self.state.clear(); self.state['pending']='year'
                return '\n\n'.join(self.catalogue.year_overview(str(y)) for y in range(1,5))+'\n\n'+YEAR_PROMPT
            year=YEAR_WORDS.get(value) or year_in(value)
            if year or value=='options': return self.choose_year(year or value)
            self.state['pending']='year'
            return (('“optio” looks incomplete. Type “options” for electives.\n' if value=='optio' else '')+YEAR_PROMPT)
        if lower in ('options','electives','elective options'):
            return self.choose_year('options')
        if re.search(r'\b(time[\s-]*table|timetables?|schedules?|class timings?|class rooms?|my classes|when.*\bclasses?\b)\b',lower):
            return self.timetable_reply(text,personal=bool(re.search(r'\bmy\b',lower)))
        new_intent=bool(re.search(r'\b(courses?|subjects?|topics?|syllabus|resources?|faculty|projects?)\b',lower))
        if self.state.get('pending')=='timetable_year' and new_intent:
            self.state['pending']=None
        if self.state.get('pending')=='timetable_section' and new_intent:
            self.state['pending']=None
        if self.state.get('pending')=='timetable_year':
            if lower in ('1','2','3','4') or year_in(lower):
                return self.timetable_reply(text,personal=self.state.get('timetable_personal',False))
            return 'Choose timetable year 1, 2, 3, or 4.'
        if self.state.get('pending')=='timetable_section':
            if timetable_section:=self.catalogue.timetable.match_section(text):
                return self.timetable_reply(timetable_section,personal=True)
            if re.search(r'\b\d{2}EC\d{1,2}\b',text,re.I) or lower=='all':
                return self.timetable_reply(text,personal=True)
            return 'Reply with a student section listed for the selected year, or type “all” to inspect the extracted year-wide rows.'
        if re.search(r'\b(notices?|deadlines?)\b',lower): return self.action('notices')
        if re.search(r'\b(notes|pyqs?|previous[- ]year (?:papers|questions))\b',lower):
            return self.action('notes' if re.search(r'\bnotes\b',lower) else 'papers')
        if (self.state.get('pending') in ('faculty_search','project_search')
                and not lower.startswith('/') and not lower.isdigit() and not year_in(lower)
                and not re.search(r'\b(courses|subjects)\b',lower)): return None
        if re.search(r'\b(faculty|professor|researcher|mentor|supervisor)\b',lower): return None
        if re.search(r'\bprojects?\b',lower): return None
        topics=bool(re.search(r'\b(topics?|syllabus|units?|start|begin)\b|what.*study|which.*study',lower))
        local_answer_request=self.assistant.llm is not None and (
                (generation_request(text) and not re.search(r'\b(topics|syllabus|units)\b',lower))
                or casual_conversation_request(text)
                or re.search(r'\bexplain\b',lower) or self.state.get('pending')=='generation')
        if local_answer_request:
            topics=False
        if re.search(r'\b(books?|chapters?|lectures?|videos?|resources?)\b',lower): topics=False
        year=year_in(lower)
        explicit_year_course_browse=bool(re.search(r'\b(courses?|subjects?)\b',lower))
        if year and (not local_answer_request or explicit_year_course_browse):
            return self.choose_year(year,topics)
        if lower.isdigit():
            if re.fullmatch(r'20\d{2}',lower):
                self.state['academic_year']=lower
                return academic_note(lower)+'\n\n'+YEAR_PROMPT
            if self.state.get('pending')=='topic' and self.state.get('topic_choices'):
                number=int(lower)
                if 1<=number<=len(self.state['topic_choices']):
                    # reply() resolves this selection to a topic, never to raw-number search.
                    return None
                return f"Choose a topic number from 1 to {len(self.state['topic_choices'])}, or type its name."
            if lower in ('1','2','3','4'): return self.choose_year(lower)
            return YEAR_PROMPT
        courses=self.catalogue.courses
        code_match=next((c for c in courses if re.search(r'(?<![A-Z0-9])'+re.escape(c['code']).replace(r'\-','-?')+r'(?![A-Z0-9])',text.upper())),None)
        name_match=next((c for c in sorted(courses,key=lambda c:-len(c['title']))
                         if c['title'].lower() in lower),None)
        chosen=code_match or name_match
        if not chosen and re.search(r'\bDSP\b',text,re.I):
            chosen=next((c for c in courses if c['title']=='Digital Signal Processing'),None)
        if lower.startswith('/course '):
            chosen=self.catalogue.course(text.partition(' ')[2])
            return self.choose_course(chosen) if chosen else 'I couldn’t find that curriculum code. '+YEAR_PROMPT
        if chosen:
            direct=self.catalogue.course(text) is not None or lower==chosen['title'].lower() or lower=='dsp'
            if direct or topics: return self.choose_course(chosen)
            if self.state.get('course')!=chosen['code']:
                self.state.pop('history',None)
                self.state.pop('last_topic',None)
                self.state.pop('search_topic',None)
                self.state.pop('syllabus_context',None)
            self.state['course']=chosen['code']
        if re.search(r'\b(courses?|subjects?|electives?)\b',lower) and not chosen:
            if re.search(r'\b(about|on|cover|covering|related|relevant|for|in)\b',lower) and not year_in(lower):
                return None
            if self.state.get('year'): return self.choose_year(self.state['year'],topics)
            self.state['pending']='year'; return YEAR_PROMPT
        if topics and not chosen:
            if self.state.get('course'):
                return self.choose_course(self.catalogue.course(self.state['course']))
            if self.state.get('year'): return self.choose_year(self.state['year'],topics=True)
            self.state['pending']='year'
            return 'Let’s choose a course first. '+YEAR_PROMPT
        if academic_year and re.fullmatch(r'(?:IIT\s*Roorkee|IITR)?\s*(?:academic\s+year\s*)?'+re.escape(academic_year),text,re.I):
            return academic_note(academic_year)+'\n\n'+YEAR_PROMPT
        if lower.startswith('/') and not lower.startswith(('/ask ','/faculty ','/search ','/resources ','/projects ')):
            return 'I didn’t recognise that command. You can ask in plain language or type “menu”.'
        return None

    def reply(self, text, faculty=False):
        if not isinstance(text,str) or not text.strip() or len(text)>1000:
            return 'Please send a question of 1–1,000 characters.'
        if text.lower().startswith('/faculty '):
            faculty=True; text=text.partition(' ')[2]
        elif text.lower().startswith(('/ask ','/search ','/resources ','/projects ')):
            self.state['pending']=None
        if faculty and text.strip().lower()=='/faculty': return self.action('faculty')
        academic_year=requested_academic_year(text)
        if academic_year: self.state['academic_year']=academic_year
        structured=self.structured_reply(text) if not faculty else None
        if structured is not None: return structured
        general=self.assistant.llm is not None and (
            generation_request(text) or casual_conversation_request(text)
            or self.state.get('pending')=='generation')
        search_query=None
        syllabus_context=None
        if general:
            unit_match=re.search(r'\b(?:unit\s+(\d+)|(first|second|third|fourth|fifth|sixth|\d+(?:st|nd|rd|th)?)\s+unit)\b',text,re.I)
            if unit_match:
                selected=self.catalogue.course(self.state['course']) if self.state.get('course') else None
                if not selected: return 'Which course do you mean? Choose its code or name, then ask about the unit.'
                unit=unit_match.group(1) or unit_match.group(2).lower()
                ordinals={'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6}
                number=ordinals[unit] if unit in ordinals else int(re.match(r'\d+',unit).group())
                units=self.catalogue.topics(selected)
                if not 1<=number<=len(units): return f'This course has {len(units)} collected syllabus units. Choose a listed unit.'
                search_query=topic_query(units[number-1][0]['text'])
                section,source=units[number-1]
                syllabus_context={'text':section['text'],'source_code':source['source_code'],
                    'url':f"https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_syll_22.pdf#page={source['pages'][0]}",
                    'metadata':{'entity_id':f"{source['syllabus_id']}:unit:{number}",'document_type':'syllabus_topic'}}
                text=f"Explain unit {number} of {selected['title']}: "+units[number-1][0]['text'][:750]
            elif re.search(r'\b(it|this|that|simpler|simplify|another example)\b',text,re.I):
                if self.state.get('last_topic'):
                    text=text+'\nTopic: '+self.state['last_topic'][:650]
                    search_query=self.state.get('search_topic')
                    syllabus_context=self.state.get('syllabus_context')
                elif not re.search(r'\b(?:explain|what is)\s+\w{3,}',text,re.I):
                    return 'Which ECE topic would you like me to explain?'
            if self.state.get('pending')=='generation':
                instruction={'explain':'Explain this topic: ','planner':'Suggest a study plan: ',
                             'roadmaps':'Suggest a learning roadmap: ','interviews':'Give ECE interview practice questions: '}
                text=instruction[self.state['generation_intent']]+text
            text=text[:1000]
        faculty=faculty or bool(re.search(r'\b(faculty|professor|researcher|mentor|supervisor)\b',text,re.I)) or self.state.get('pending')=='faculty_search'
        projects=bool(re.search(r'\bprojects?\b',text,re.I)) or self.state.get('pending')=='project_search'
        if (faculty or projects) and re.search(r'\b(relevant|related|this course|this topic)\b',text,re.I):
            selected=self.catalogue.course(self.state['course']) if self.state.get('course') else None
            topic=selected['title'] if selected else self.state.get('last_topic')
            if not topic:
                self.state['pending']='faculty_search' if faculty else 'project_search'
                return 'Which topic or course should I use to find relevant '+('faculty?' if faculty else 'projects?')
            text=topic
        if text.strip().isdigit():
            text=topic_query(self.state['topic_choices'][int(text.strip())-1])
        if text.lower().startswith('/faculty '): faculty=True; text=text.partition(' ')[2]
        elif text.lower().startswith(('/ask ','/search ','/resources ','/projects ')): text=text.partition(' ')[2]
        self.state['pending']=None
        self.state['last_topic']=text
        self.state['search_topic']=search_query or text
        self.state['syllabus_context']=syllabus_context
        if projects:
            answer=self.assistant.project_reply(text,history=self.state.get('history'))
        else:
            answer=self.assistant.reply(text,self.state.get('course'),faculty,self.state.get('academic_year',DEFAULT_ACADEMIC_YEAR),
                                        history=self.state.get('history'),general=general,search_query=search_query,syllabus=syllabus_context)
        if self.assistant.llm is not None:
            history=self.state.setdefault('history',[])
            history.append({'question':text[:300],'answer':re.sub(r'<[^>]+>','',answer)[:400]})
            del history[:-2]
        if self.state.get('academic_year') and academic_note(self.state['academic_year']) not in answer:
            answer=academic_note(self.state['academic_year'])+'\n\n'+answer
        return answer
