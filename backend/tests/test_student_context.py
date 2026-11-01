from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from backend.app import main, academic_context as context
from backend.app.config import Settings
from backend.app.db import make_engine
from backend.app.data import read_records

@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(main,'ENGINE',make_engine('sqlite:///:memory:'))
    monkeypatch.setattr(main,'SETTINGS',Settings(_env_file=None))
    with TestClient(main.app) as client:
        session=client.post('/api/v1/sessions').json()
        headers={'X-Session-Token':session['session_token']}
        r=client.put('/api/v1/sessions/'+session['session_id']+'/profile',headers=headers,json={'study_year':3,'section':'24EC1','semester':5,'academic_cohort':None})
        assert r.status_code==200
        cid=client.post('/api/v1/sessions/'+session['session_id']+'/conversations',headers=headers).json()['conversation_id']
        def send(text):
            response=client.post('/api/v1/conversations/'+cid+'/messages',headers=headers,json={'text':text})
            assert response.status_code==200, response.text
            return response.json()['assistant_message']
        send.client = client
        send.profile_url = '/api/v1/sessions/'+session['session_id']+'/profile'
        send.headers = headers
        yield send

@pytest.mark.parametrize('query',['3rd year timetable','Third year ECE timetable','3rd year timetabel'])
def test_complete_year(chat,query):
    result=chat(query)
    expected=[r for r in read_records('timetable') if r['study_year']==3]
    assert {r['record_id'] for r in result['data']}=={r['record_id'] for r in expected}
    assert {'Lecture','Practical','Tutorial'} <= {r['session_type'] for r in result['data']}

@pytest.mark.parametrize('query',['my timetable','weekly timetable','show my complete schedule'])
def test_personal_schedule(chat,query):
    result=chat(query)
    expected=[r for r in read_records('timetable') if r['study_year']==3 and r['course_code'] in {'ECC-301','ECC-303','ECC-305','ECC-351'} and (not r['student_sections'] or '24EC1' in r['student_sections'])]
    assert {r['record_id'] for r in result['data']}=={r['record_id'] for r in expected}
    assert any(r['section_scope']=='section not specified' for r in result['data'])

def test_exams_and_faculty_followup(chat):
    result=chat('ETE schedule')
    _,codes=context.timetable_context({'study_year':3,'section':'24EC1','semester':5})
    expected=[r for r in read_records('exams') if r.get('course_code') in codes]
    assert result['data'] and {r['record_id'] for r in result['data']}=={r['record_id'] for r in expected}
    result=chat('Who teaches it?')
    assert result['data'] and all(r['course_code'] in codes for r in result['data'])
    assert chat('ETE faculty')['data']

def test_courses_and_abbreviations(chat):
    assert chat('ECC303')['data'][0]['code']=='ECC-303'
    assert chat('microwve course')['data'][0]['code']=='ECC-303'
    assert {r['code'] for r in chat('ECC-301 and ECC-303')['data']}=={'ECC-301','ECC-303'}
    assert chat('my core subjects')['data']
    assert 'Which course' in chat('ETE syllabus')['content']
    assert 'Which course' in chat('professor projects')['content']

def test_relative_days(chat,monkeypatch):
    monkeypatch.setattr(context,'now_kolkata',lambda:datetime(2026,11,1,12,tzinfo=ZoneInfo('Asia/Kolkata')))
    result=chat('What classes do I have tomorrow?')
    assert result['data'] and all(r['day']=='Monday' and r['date']=='2026-11-02' for r in result['data'])
    assert all(r['day']=='Monday' for r in chat('My Monday schedule')['data'])
    assert all(r['day']=='Friday' for r in chat('What is happening on Friday?')['data'])
    assert chat("Today's classes")['data']==[]

def test_large_and_missing_metadata(monkeypatch):
    base=read_records('timetable')[0]
    rows=[dict(base,record_id=str(i),study_year=3,student_sections=[]) for i in range(150)]
    original=context.read_records
    monkeypatch.setattr(context,'read_records',lambda k: rows if k=='timetable' else original(k))
    result=context.resolve('3rd year timetable',None,[])
    assert len(result['data'])==150
    assert 'Select your study year' in context.resolve('my timetable',None,[])['content']

def test_learning_does_not_search_records(chat):
    result=chat('help me learn my microwave course')
    assert result['presentation']=='answer' and result['data'] is None


def test_professor_context_and_projects(chat):
    chat('ECC303')
    assert chat('Who teaches it?')['data'][0]['faculty']=='Akhilesh Mohan'
    details=chat('Tell me about this professor')
    assert details['data'][0]['name']=='Akhilesh Mohan'
    assert chat('their projects')['data']
    assert chat('Sparsh Mittal projects')['data']


def test_model_tools_default_to_student_courses(chat):
    profile={'study_year':3,'section':'24EC1','semester':5}
    _,codes=context.timetable_context(profile)
    assert {r['course_code'] for r in main._tool_data('get_exams',{},profile)['exams']} <= codes
    assert main._tool_data('get_profile',{},profile)['institution']=='IIT Roorkee ECE'


def test_source_preservation():
    import json
    from pathlib import Path
    source=json.loads(Path('datafiles/master_timetable_by_year.json').read_text(encoding='utf-8'))
    rows=read_records('timetable')
    assert len(rows)==sum(map(len,source.values()))
    for i,key in enumerate(('I-Year','II-Year','III-Year','IV-Year'),1):
        actual=[r for r in rows if r['study_year']==i]
        assert len(actual)==len(source[key])
        for a,b in zip(actual,source[key]):
            assert all(a.get(k)==b.get(k) for k in ('course_code','day','start_time','end_time','session_type','room','faculty'))


@pytest.mark.parametrize('hss,oec', [(None,None),('HSS-302',None),(None,'ECO-101'),('HSS-305','ECO-102')])
def test_elective_selection_persistence_and_schedule(chat,hss,oec):
    payload={'study_year':3,'section':'24EC1','semester':5,'hss_course':hss,'oec_course':oec}
    response=chat.client.put(chat.profile_url,headers=chat.headers,json=payload)
    assert response.status_code==200, response.text
    restored=chat.client.get(chat.profile_url,headers=chat.headers).json()['profile']
    assert restored['hss_course']==hss and restored['oec_course']==oec
    if hss: assert restored['hss_course_name']
    result=chat('my timetable')
    core={'ECC-301','ECC-303','ECC-305','ECC-351'}
    expected=[r for r in read_records('timetable') if r['study_year']==3 and
              r['course_code'] in core | ({hss} if hss else set()) and
              (not r['student_sections'] or '24EC1' in r['student_sections'])]
    assert {r['record_id'] for r in result['data']}=={r['record_id'] for r in expected}
    if oec:
        assert any(oec in note and 'schedule unavailable' in note for note in result['warnings'])
        assert not any(r['course_code']=='OEC' for r in result['data'])
    if hss:
        assert chat('What is my HSS course?')['data'][0]['code']==hss
        assert all(r['course_code']==hss for r in chat('When is my HSS class?')['data'])
        assert chat('Who teaches it?')['data']
    # Authenticated dedicated endpoint uses the same complete personalized result.
    direct=chat.client.get(chat.profile_url.replace('/profile','/timetable'),headers=chat.headers)
    assert direct.status_code==200
    assert {r['record_id'] for r in direct.json()['records']}=={r['record_id'] for r in expected}


def test_optional_course_validation_and_refresh(chat):
    options=chat.client.get('/api/v1/profile-options?study_year=3&semester=5').json()['optional_courses']
    assert {r['code'] for r in options['hss']}=={'HSS-302','HSS-304','HSS-305','HSS-306'}
    assert all(r['title'] and r['code'] for values in options.values() for r in values)
    assert chat.client.get('/api/v1/profile-options?study_year=3&semester=6').json()['optional_courses']=={'hss':[],'oec':[]}
    base={'study_year':3,'section':'24EC1','semester':5}
    for fields in ({'hss_course':'HSS-999'},{'hss_course':'ECO-101'},{'oec_course':'HSS-302'},
                   {'hss_course':'HSS-302','oec_course':'HSS-302'},{'semester':6,'hss_course':'HSS-302'}, {'semester':3}):
        assert chat.client.put(chat.profile_url,headers=chat.headers,json={**base,**fields}).status_code==422
    for code in ('HSS-302','HSS-305',None):
        assert chat.client.put(chat.profile_url,headers=chat.headers,json={**base,'hss_course':code}).status_code==200
        timetable=chat('my timetable')['data']
        assert {r['course_code'] for r in timetable if r['course_code'].startswith('HSS')}==({code} if code else set())


@pytest.mark.parametrize('query,heading',[
    ('Tell me about Vinod Pankajakshan','Research Interests'),
    ('Tell me about Pankajakshan','Educational Details'),
    ('What are his research interests?','Research Interests'),
    ('What courses does he teach?','Teaching Engagements'),
    ('What is his academic background?','Educational Details'),
    ('What are his publications?','Publications'),
])
def test_faculty_queries_against_uploaded_profile(chat,query,heading):
    chat('Tell me about Vinod Pankajakshan')
    result=chat(query)
    record=result['data'][0]
    assert record['faculty_id']=='iitr-ece-100564'
    source=next(f for f in read_records('faculty') if f['faculty_id']==record['faculty_id'])
    expected=[s['text'] for s in source['sections'] if s['heading']==heading and s['text']]
    assert expected and all(text in [s['text'] for s in record['profile_sections']] for text in expected)
    assert result['sources']
    if heading=='Teaching Engagements':
        assert {r['course_code'] for r in record['teaching_assignments']}=={'ECC-201'}
        assert 'ECN-312' in str(record['profile_sections'])


def test_complete_faculty_cross_document_projects_and_ambiguity(chat):
    result=chat('Show me all information about Vinod Pankajakshan')
    record=result['data'][0]
    source=next(f for f in read_records('faculty') if f['name']=='Vinod Pankajakshan')
    assert {s['text'] for s in record['profile_sections']}=={s['text'] for s in source['sections'] if s.get('text') or s.get('tables')}
    assert len(record['projects'])==3
    assert len(chat('What projects has he worked on?')['data'])==3
    ambiguous=chat('Tell me about Kumar')
    assert ambiguous['data'] is None and 'Which professor' in ambiguous['content']


def test_clashes_are_highlighted_without_losing_rows():
    from backend.app.electives import annotate_clashes
    rows=[{'record_id':'core','course_code':'ECC-303','day':'Monday','start_time':'09:00','end_time':'10:00'},
          {'record_id':'hss','course_code':'HSS-302','day':'Monday','start_time':'09:30','end_time':'10:30'},
          {'record_id':'adjacent','course_code':'ECC-301','day':'Monday','start_time':'10:30','end_time':'11:30'}]
    result=annotate_clashes(rows+[rows[0]])
    assert len(result)==3
    assert result[0]['clashes_with']==['HSS-302'] and result[1]['clashes_with']==['ECC-303']
    assert not result[2]['clashes_with']


def test_additive_profile_migration_preserves_existing_rows():
    from backend.app.db import ensure_compat_schema
    from sqlalchemy import inspect
    engine=make_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE profiles (session_id TEXT PRIMARY KEY, study_year INTEGER, section TEXT, semester INTEGER)')
        conn.exec_driver_sql("INSERT INTO profiles VALUES ('old-session',3,'24EC1',5)")
    ensure_compat_schema(engine)
    ensure_compat_schema(engine)
    assert {'hss_course','oec_course'} <= {c['name'] for c in inspect(engine).get_columns('profiles')}
    with engine.connect() as conn:
        row=conn.exec_driver_sql('SELECT * FROM profiles').mappings().one()
        assert row['session_id']=='old-session' and row['hss_course'] is None and row['oec_course'] is None
