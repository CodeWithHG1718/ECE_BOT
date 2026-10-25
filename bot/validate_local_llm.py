"""Exercise real local BGE-M3 + Qwen, saving a presentation-ready sample transcript."""
import json
from pathlib import Path
import re
from time import perf_counter

from bot.assistant import StudyAssistant
from bot.conversation import Conversation
from bot.local_chat import LazyRetriever, plain
from bot.local_llm import OllamaChat

ROOT=Path(__file__).resolve().parents[1]


class MeasuredChat(OllamaChat):
    def __init__(self): super().__init__(); self.calls=0
    def generate(self,*args,**kwargs):
        self.calls+=1
        return super().generate(*args,**kwargs)


def main():
    model=MeasuredChat()
    if not model.status(): raise SystemExit('Run Start-Signal.ps1 first; the local Qwen model must be installed and available.')
    assistant=StudyAssistant(LazyRetriever(),llm=model)
    chat=Conversation(assistant)
    report=[]; transcript=['# Actual local LLM walkthrough','',
                          'Local Qwen3 4B Instruct and BGE-M3. No Telegram or paid API calls.','']

    def check(question, predicate, generated=True):
        before=model.calls; model.last_stats={}
        start=perf_counter(); answer=chat.reply(question); elapsed=perf_counter()-start
        text=plain(answer)
        passed=bool(predicate(text)) and (model.calls>before if generated else model.calls==before)
        report.append({'question':question,'passed':passed,'wall_seconds':round(elapsed,3),
                       'generation_calls':model.calls-before,'generation':model.last_stats.copy()})
        transcript.extend(['## '+question,'',text,'',f'Elapsed: {elapsed:.2f} seconds.',''])
        print(('PASS' if passed else 'FAIL')+f' {elapsed:.2f}s: '+question,flush=True)
        return text

    check('Show me courses of 2nd year at IIT Roorkee in 2026',
          lambda a:all(c['code'] in a for c in assistant.catalogue.year_courses('2')) and 'Semester 4' in a,False)
    chat.reply('/clear')
    check('Explain convolution in simple terms.',lambda a:'General study guidance' in a and 'convolution' in a.lower())
    check('Give a numerical example: convolve [1, 2] with [1, 1].',
          lambda a:'General study guidance' in a and bool(re.search(r'1\s*,\s*3\s*,\s*2',a)))
    check('DSP',lambda a:'ECC-301' in a and 'Sampling and Quantization' in a,False)
    check('Explain the second unit',lambda a:'Syllabus study guide' in a and 'sampl' in a.lower()
          and not re.search(r'band.pass[^.]*require[^.]*non.uniform',a,re.I))
    check('Make it simpler',lambda a:'Syllabus study guide' in a and ('sampl' in a.lower() or 'quantiz' in a.lower())
          and not re.search(r'band.pass[^.]*require[^.]*non.uniform',a,re.I))
    check('Show my timetable',lambda a:'Which study year' in a,False)
    check('Choose Year 2 for the timetable',lambda a:'25EC1' in a,False)
    check('Choose section 25EC1',lambda a:'ECC-205' in a and 'OCR-extracted weekly entries' in a,False)
    check('I am a 2nd year from ECE-3 batch; show my timetable',
          lambda a:'Year 2 timetable' in a and '25EC3' in a and 'ECC-205' in a,False)
    check('Who is the professor for ECT-108?',
          lambda a:'Saurabh Khanna' in a and 'team-supplied' in a and 'not been independently verified' in a,False)
    check("Hey, how's it going?",lambda a:bool(a.strip()))
    check('/projects VLSI',lambda a:'Related departmental project records' in a and 'not confirmed current openings' in a,False)
    chat=Conversation(assistant)
    check('only books about convolution',lambda a:'Study guidance' in a and 'Read' in a and 'Watch' not in a)
    chat=Conversation(assistant)
    check('Explain convolution in simple terms.',lambda a:'General study guidance' in a)
    gpu_models=model._request('/api/ps').get('models',[])
    report_data={'model':model.model,'endpoint':model.base_url,'checks':report,
                 'all_passed':all(r['passed'] for r in report),
                 'running_models':[{k:m.get(k) for k in ('name','digest','size','size_vram','context_length')} for m in gpu_models],
                 'limitations':'Small developer-authored functional sample, not a comprehensive educational accuracy benchmark.'}
    (ROOT/'docs/local-llm-validation.json').write_text(json.dumps(report_data,indent=2),encoding='utf-8')
    (ROOT/'docs/local-llm-demo.md').write_text('\n'.join(transcript),encoding='utf-8')
    if not report_data['all_passed']: raise SystemExit('Some local LLM checks failed; inspect docs/local-llm-demo.md.')


if __name__=='__main__': main()
