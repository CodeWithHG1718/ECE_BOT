"""Run real local chatbot smoke checks and save a readable demonstration."""
import json
from time import perf_counter
from bot.assistant import StudyAssistant
from bot.catalogue import ROOT
from bot.local_chat import plain
from ingestion.bge_embeddings import Retriever


def main():
    assistant=StudyAssistant(Retriever())
    cases=[
        ('Where should I learn convolution?','ECC-106',False,'Linear Time-Invariant Systems'),
        ('Which lectures explain digital logic?','ECC-104',False,'Watch'),
        ('What are the credits for ECC-203?',None,False,'Electromagnetics'),
        ('VLSI',None,True,'supervision'),
        ('how to bake a chocolate cake',None,False,'couldn’t find'),
        ('What are the credits for ECN-203?','ECC-106',False,'isn’t in the supplied curriculum'),
        ('Circuits that combine gates without storing any state','ECC-104',False,None),
    ]
    report=[]; transcript=['# Local Signal chatbot demonstration','',
        'Actual BGE-M3 retrieval and source-backed templates. No Telegram token, external messages, or paid generation API.','']
    for query,course,faculty,expected in cases:
        start=perf_counter(); answer=plain(assistant.reply(query,course,faculty))
        seconds=round(perf_counter()-start,4)
        passed=expected in answer if expected else None
        report.append({'query':query,'course':course,'passed':passed,'seconds':seconds,'answer':answer})
        transcript += [f'## {query}',f'Course filter: {course or "all"} · {seconds}s','',answer,'']
    (ROOT/'docs/local-chatbot-demo.md').write_text('\n'.join(transcript),encoding='utf-8')
    (ROOT/'docs/local-chatbot-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checked':sum(r['passed'] is not None for r in report),
        'passed':sum(r['passed'] is True for r in report),'transcript':'docs/local-chatbot-demo.md'},indent=2))
    if any(r['passed'] is False for r in report): raise SystemExit(1)


if __name__=='__main__': main()
