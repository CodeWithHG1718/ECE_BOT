"""Application-owned menu/actions: the model never invents buttons or URLs."""
SECTIONS = {
    'academics': ('Academics', 'Courses, curriculum and academic information',
                  ('courses','timetable','dates','rules')),
    'learning': ('Courses & Learning', 'Syllabus topics, books and lectures',
                 ('courses','resources','notes','papers')),
    'faculty': ('Faculty & Research', 'Research interests and recorded departmental projects',
                ('faculty','projects','research','labs')),
    'career': ('Projects & Career', 'Research projects and future career-support tools',
               ('projects','roadmaps','internships','interviews')),
    'department': ('Department & Campus', 'Official contacts, facilities and procedures',
                   ('contacts','labs','facilities','forms')),
    'notices': ('Notices & Updates', 'Notices, events and reminders',
                ('notices','events','reminders')),
    'assistant': ('AI Assistant', 'Ask across the collected study resources',
                  ('search','planner','explain')),
}
ACTIONS = {
    'courses':'Browse Courses', 'timetable':'My Timetable', 'dates':'Exams & Dates',
    'rules':'Academic Rules', 'resources':'Find Resources', 'notes':'Find Notes',
    'papers':'Previous-year Papers', 'faculty':'Find Faculty', 'projects':'Explore Projects',
    'research':'Research Areas', 'labs':'Find a Lab', 'roadmaps':'Skill Roadmaps',
    'internships':'Internships', 'interviews':'Interview Prep', 'contacts':'Contacts',
    'facilities':'Facilities', 'forms':'Forms & Policies', 'notices':'Latest Notices',
    'events':'Upcoming Events', 'reminders':'My Reminders', 'search':'Ask a Question',
    'planner':'Study Planner', 'explain':'Explain a Topic', 'topics':'Syllabus Topics',
    'related_faculty':'Related Faculty',
}
UNAVAILABLE = {
    'dates':'A verified academic calendar and exam schedule have not been added. I can’t confirm dates yet.',
    'rules':'A complete verified academic-rules catalogue has not been added. I can give course credits and semesters from the supplied curriculum.',
    'notes':'Official lecture notes have not been added. Books and NPTEL lectures are available through Find Resources, labelled as external study material.',
    'papers':'Previous-year question papers have not been added. I won’t invent papers or download links.',
    'labs':'A verified lab directory with locations and access details has not been added.',
    'roadmaps':'Personalised skill roadmaps need the answer-model integration. You can explore courses, resources and recorded research projects now.',
    'internships':'Verified internship listings and application deadlines have not been added.',
    'interviews':'Interactive interview practice needs the answer-model integration.',
    'contacts':'A verified departmental contact directory has not been added to this interface. Find Faculty provides official faculty profile links.',
    'facilities':'A verified facilities directory has not been added.',
    'forms':'Verified administrative forms and policy links have not been added.',
    'notices':'A current official notices feed has not been connected. I can’t confirm the latest notices.',
    'events':'A current official events feed has not been connected.',
    'reminders':'Reminder scheduling has not been implemented. No reminder has been created.',
    'planner':'Personalised study planning needs the answer-model integration. You can browse syllabus topics and find their resources now.',
    'explain':'Generated explanations and quizzes are not connected yet. I can show syllabus topics and recommend chapters or lectures.',
}


def main_menu():
    return ('<b>ECE Companion · Signal</b>\nYour department, all in one place.\n\n'
            'Hey! Welcome to your ECE Companion. What do you need help with today?\n\n'
            + '\n'.join(f'<b>{label}</b> — {description}' for label,description,_ in SECTIONS.values())
            + '\n\nChoose a section or ask directly: “Show me courses of 2nd year”.'
            '\nCourses, topics, resources, faculty and recorded research projects are available; '
            'other sections explain what still needs to be added.'
            '\nType “menu” to return here. In local chat, /quit exits.')


def section_menu(key):
    label,description,actions=SECTIONS[key]
    return f'<b>{label}</b>\n{description}\n\n'+'\n'.join(ACTIONS[a] for a in actions)+ \
        '\n\nChoose an option, type your question, or return to Main Menu.'
