"""Small source-grounded smoke set, not a substitute for student relevance review."""
import json
from pathlib import Path
from time import perf_counter
from bge_embeddings import Retriever, ROOT

CASES = [
    {'query': 'Where can I learn how convolution describes an LTI system?', 'course': 'ECC-106', 'expected': 'oppenheim-signals-2:chapter:2'},
    {'query': 'Representing periodic signals as sums of sinusoids', 'course': 'ECC-106', 'expected': 'oppenheim-signals-2:chapter:3'},
    {'query': 'What should I read about the Laplace transform?', 'course': 'ECC-106', 'expected': 'oppenheim-signals-2:chapter:9'},
    {'query': 'Transmission line impedance and reflected waves', 'course': 'ECC-303', 'expected': 'pozar-microwave-3:chapter:2'},
    {'query': 'Microwave impedance matching using stubs', 'course': 'ECC-303', 'expected': 'pozar-microwave-3:chapter:5'},
    {'query': 'Which chapter covers microwave filter design?', 'course': 'ECC-303', 'expected': 'pozar-microwave-3:chapter:8'},
]
NEGATIVES = ['xyzzynotarealtopic', 'how to bake a chocolate cake', 'latest cricket match score']
HOLDOUT = [
    ('How do I simplify digital logic using Boolean algebra?', 'ECC-104', 'mano-digital-6:chapter:2'),
    ('Study registers and binary counters', 'ECC-104', 'mano-digital-6:chapter:6'),
    ('Circuits that combine gates without storing any state', 'ECC-104', 'mano-digital-6:chapter:4'),
    ('Where should I study diode models and rectifier circuits?', 'ECC-102', 'razavi-fundamentals-2:chapter:3'),
    ('Device physics of a MOS transistor', 'ECC-102', 'razavi-fundamentals-2:chapter:6'),
    ('Design using operational amplifiers', 'ECC-204', 'razavi-fundamentals-2:chapter:8'),
    ('Differential amplifier circuits', 'ECC-204', 'razavi-fundamentals-2:chapter:10'),
    ('Linear and planar arrays of antennas', 'ECC-203', 'balanis-antennas-3:chapter:6'),
    ('How to design a patch antenna on a printed circuit board', 'ECC-203', 'balanis-antennas-3:chapter:14'),
    ('Amplitude modulation of a carrier signal', 'ECC-201', 'haykin-intro-communications-2:chapter:3'),
    ('Random signals and noise in communication', 'ECC-201', 'haykin-intro-communications-2:chapter:8'),
    ('Error correcting codes for digital communication', 'ECC-202', 'haykin-digital-communications-1:chapter:10'),
    ('Entropy and information theory', 'ECC-202', 'haykin-digital-communications-1:chapter:5'),
    ('Sampling a continuous signal to make a discrete time sequence', 'ECC-301', 'oppenheim-dsp-3:chapter:4'),
    ('Fast algorithms for computing the discrete Fourier transform', 'ECC-301', 'oppenheim-dsp-3:chapter:9'),
    ('Designing a digital filter', 'ECC-301', 'oppenheim-dsp-3:chapter:7'),
]
HOLDOUT_NEGATIVES = ['recommend a pasta recipe', 'Who won the football world cup?', 'qzxvblnmp', 'cheap hotels in Paris']
COURSE_CASES = [
    {'query': 'Which elective covers adaptive signal processing?', 'expected_code': 'ECL-614'},
    {'query': 'Which course teaches network theory?', 'expected_code': 'ECC-205'},
]
TIMETABLE_CASES = [
    {'query': 'What class is scheduled for Network Theory in the second year?', 'expected_code': 'ECC-205'},
]
COURSE_FACULTY_CASES = [
    {'query': 'Who is the professor for ECT-108?', 'expected_code': 'ECT-108',
     'expected_name': 'Saurabh Khanna'},
]


def main():
    retriever = Retriever()
    checks = []
    for case in CASES + [{'query':q,'course':c,'expected':e,'split':'holdout'} for q,c,e in HOLDOUT]:
        start = perf_counter()
        hits = retriever.search(case['query'], case['course'], ['book_chapter'], limit=5)
        ids = [h['metadata']['entity_id'] for h in hits]
        rank = ids.index(case['expected'])+1 if case['expected'] in ids else None
        checks.append({'split':'development',**case, 'expected_rank': rank, 'passed': rank is not None,
            'seconds': round(perf_counter()-start,3), 'results': [
                {'id':h['metadata']['entity_id'],'text':h['text'],'scores':h['scores']} for h in hits]})
    negatives = []
    for query in NEGATIVES+HOLDOUT_NEGATIVES:
        hits = retriever.search(query, types=['book_chapter','nptel_lecture'])
        negatives.append({'query':query,'abstained':not hits,'results':[
            {'id':h['metadata']['entity_id'],'scores':h['scores']} for h in hits]})
    course_checks = []
    for case in COURSE_CASES:
        hits = retriever.search(case['query'], types=['curriculum_entry', 'workbook_course'], limit=5)
        codes = [h['metadata'].get('course_code') for h in hits]
        rank = codes.index(case['expected_code']) + 1 if case['expected_code'] in codes else None
        course_checks.append({**case, 'expected_rank': rank, 'passed': rank is not None,
            'results': [{'code':h['metadata'].get('course_code'), 'text':h['text'], 'scores':h['scores']} for h in hits]})
    timetable_checks = []
    for case in TIMETABLE_CASES:
        hits = retriever.search(case['query'], types=['timetable_record'], limit=5)
        codes = [h['metadata'].get('course_code') for h in hits]
        rank = codes.index(case['expected_code']) + 1 if case['expected_code'] in codes else None
        timetable_checks.append({**case, 'expected_rank': rank, 'passed': rank is not None,
            'results': [{'code':h['metadata'].get('course_code'), 'text':h['text'], 'scores':h['scores']} for h in hits]})
    course_faculty_checks = []
    for case in COURSE_FACULTY_CASES:
        hits = retriever.search(case['query'], types=['course_faculty_assignment'], limit=5)
        rank = next((index+1 for index,hit in enumerate(hits)
                     if hit['metadata'].get('course_code')==case['expected_code']
                     and hit['metadata'].get('faculty_name')==case['expected_name']),None)
        course_faculty_checks.append({**case, 'expected_rank': rank, 'passed': rank is not None,
            'results': [{'code':h['metadata'].get('course_code'), 'faculty':h['metadata'].get('faculty_name'),
                         'text':h['text'], 'scores':h['scores']} for h in hits]})
    start=perf_counter(); retriever.search(CASES[0]['query'],CASES[0]['course'],['book_chapter'],5)
    repeated_seconds=round(perf_counter()-start,4)
    report = {'scope':'Developer-authored smoke set: 6 development and 16 held-out chapter queries, course/timetable/faculty examples, plus 7 unrelated queries. Not a benchmark or guarantee.',
        'model':retriever.manifest['embedding'], 'positive_hit_at_5':sum(c['passed'] for c in checks)/len(checks),
        'positive_hit_at_2':sum(c['expected_rank'] is not None and c['expected_rank']<=2 for c in checks)/len(checks),
        'holdout_hit_at_5':sum(c['passed'] for c in checks if c['split']=='holdout')/len(HOLDOUT),
        'course_search_hit_at_5':sum(c['passed'] for c in course_checks)/len(course_checks),
        'timetable_search_hit_at_5':sum(c['passed'] for c in timetable_checks)/len(timetable_checks),
        'course_faculty_hit_at_5':sum(c['passed'] for c in course_faculty_checks)/len(course_faculty_checks),
        'negative_abstentions':sum(n['abstained'] for n in negatives), 'negative_count':len(negatives),
        'repeat_query_seconds':repeated_seconds,'checks':checks,'course_checks':course_checks,
        'timetable_checks':timetable_checks,'course_faculty_checks':course_faculty_checks,
        'negatives':negatives}
    path = ROOT/'docs/embedding-evaluation.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('checks','negatives')},indent=2))
    print(f'Detailed results: {path}')


if __name__ == '__main__':
    main()
