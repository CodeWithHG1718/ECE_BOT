"""Bounded, local-only Ollama generation with validated output and no cloud fallback."""
from collections import OrderedDict
from html import escape
import json
import os
from pathlib import Path
import re
from time import monotonic
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler

from bot.prompts import build_answer_messages

MODEL = 'qwen3:4b-instruct'
PORTABLE_RUNTIME = Path(__file__).resolve().parents[1]/'.cache/ollama-v0.24.0/ollama.exe'


def default_endpoint():
    return 'http://127.0.0.1:11435' if PORTABLE_RUNTIME.exists() else 'http://127.0.0.1:11434'

SCHEMA = {
    'type':'object', 'properties':{
        'answer':{'type':'string'},
        'source_ids':{'type':'array','items':{'type':'string'}},
    }, 'required':['answer','source_ids'], 'additionalProperties':False,
}


class LocalModelError(RuntimeError):
    pass


def generation_request(text):
    return bool(re.search(
        r'\b(explain|explanation|compare|difference|roadmap|study plan|quiz|practice question)\b'
        r'|\bwhat (?:is|are)\b|\bhow (?:does|do|can|should)\b'
        r'|\b(?:simpler|simplify|example|chip design.*start|start.*chip design)\b',text,re.I))


class OllamaChat:
    model = MODEL

    def __init__(self, base_url=None, timeout=90):
        self.base_url=(base_url or os.getenv('SIGNAL_OLLAMA_URL') or default_endpoint()).rstrip('/')
        parsed=urlparse(self.base_url)
        if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('SIGNAL_OLLAMA_URL must be a local HTTP loopback address.')
        self.timeout=timeout
        self.cache=OrderedDict()
        self.last_stats={}
        # Never send local chat through an HTTP proxy configured on the machine.
        self.opener=build_opener(ProxyHandler({}))

    def _request(self, path, payload=None, timeout=None):
        request=Request(self.base_url+path,
                        data=json.dumps(payload).encode('utf-8') if payload is not None else None,
                        headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=timeout or self.timeout) as response:
                raw=response.read(1_000_001)
            if len(raw)>1_000_000: raise ValueError('Oversized model response')
            result=json.loads(raw)
            if not isinstance(result,dict): raise ValueError('Expected a JSON object')
            return result
        except Exception as exc:
            # Do not log prompts or return local server internals to students.
            raise LocalModelError('Local model request failed.') from exc

    def status(self):
        try:
            models=self._request('/api/tags',timeout=3).get('models',[])
            return any(m.get('name')==self.model for m in models)
        except LocalModelError:
            return False

    def warmup(self):
        """Load the model before a presentation; no user prompt or transcript needed."""
        self._request('/api/chat',{'model':self.model,'messages':[{'role':'user','content':'Reply READY.'}],
                      'stream':False,'keep_alive':'10m','options':{'num_ctx':4096,'num_predict':1}})

    @staticmethod
    def evidence(hits):
        """Bound source context, deduplicate entities, and assign application-owned IDs."""
        records=[]; seen=set()
        for hit in hits:
            metadata=hit.get('metadata',{})
            entity=metadata.get('entity_id')
            if not entity or entity in seen or not hit.get('text'): continue
            seen.add(entity)
            records.append({'id':f'S{len(records)+1}', 'type':metadata.get('document_type'),
                            'text':hit['text'][:1100]})
            if len(records)==4: break
        return records

    def generate(self, question, hits, *, course=None, academic_year=None, history=None, mode='grounded'):
        records=self.evidence(hits)
        if mode in ('grounded','overview') and not records:
            raise LocalModelError('No usable evidence for a grounded answer.')
        messages=build_answer_messages(question,records,course=course,academic_year=academic_year)
        instructions=(
            '\nReturn JSON with exactly answer (plain text) and source_ids (array of S1-style IDs). '
            'Write at most 160 words, in short paragraphs. No HTML, URLs, Markdown links or invented '
            'source identifiers. The application adds verified links separately. '
            'Put source IDs only in source_ids, not in the answer text. '
            'Do not output a list of course codes or change official facts. '
            'Answer only the requested task. Do not add a quiz or a roadmap unless requested. '
        )
        if mode=='overview':
            instructions+=('Give a beginner-friendly guide to WHAT TO STUDY using the supplied syllabus_topic '
                           'record. Group or simplify its listed topics. Do not derive technical rules, guarantees '
                           'or necessary conditions from a list of topic names. In particular, a list mentioning '
                           'two methods does not prove that a particular signal type requires one of them. '
                           'Do not add formulas, facts or prerequisites absent from that outline. Include the '
                           'syllabus record ID in source_ids. Leave book/lecture recommendations to the app.')
        elif mode=='general':
            instructions+=('Give a useful ECE explanation, worked example, quiz or study plan as requested. '
                           'This is general educational guidance, not an official IIT Roorkee answer or '
                           'a quote from a textbook. Outline-only evidence identifies study resources, '
                           'not the full source of your explanation. Do not invent institute-specific facts. '
                           'Explain the concepts directly. Do not name books, chapters, lectures, course '
                           'codes or academic years in the explanation; the app supplies that metadata '
                           'and resource list separately. For a calculation, check every output term and '
                           'show all steps needed to obtain the result. '
                           'Use [] for source_ids unless you actually discuss a supplied record. '
                           'For unrelated non-educational requests, briefly redirect to ECE study help.')
        else:
            instructions+=('Summarize why the supplied records are useful for the question. Use ONLY '
                           'these records; include at least one of their IDs in source_ids. '
                           'Do not claim that topic outlines contain full explanations or solutions.')
        messages[0]['content']+=instructions
        payload=json.loads(messages[1]['content'])
        payload['recent_conversation']=[{'question':t['question'][:300],'answer':t['answer'][:400]}
                                        for t in (history or [])[-2:]] if mode=='general' else []
        messages[1]['content']=json.dumps(payload,ensure_ascii=False)
        body={'model':self.model,'messages':messages,'stream':False,'format':SCHEMA,
              'keep_alive':'10m','options':{'temperature':0.2,'num_ctx':4096,'num_predict':450}}
        key=json.dumps(body,sort_keys=True)
        if key in self.cache:
            self.cache.move_to_end(key)
            self.last_stats={'cached':True,'wall_seconds':0}
            return self.cache[key]
        start=monotonic()
        response=self._request('/api/chat',body)
        try:
            if not isinstance(response,dict) or response.get('done') is not True or response.get('done_reason')=='length':
                raise ValueError('Incomplete generation')
            result=json.loads(response['message']['content'])
            answer=result['answer']; ids=result['source_ids']
            valid={r['id'] for r in records}
            syllabus_ids={r['id'] for r in records if r.get('type')=='syllabus_topic'}
            if (not isinstance(answer,str) or not answer.strip() or len(answer)>2400
                    or not isinstance(ids,list) or any(not isinstance(i,str) or i not in valid for i in ids)
                    or (mode in ('grounded','overview') and not ids)
                    or (mode=='overview' and not any(i in syllabus_ids for i in ids))
                    or re.search(r'https?://|www\.|\]\(|<a\b',answer,re.I)):
                raise ValueError('Invalid generated answer')
        except (KeyError,TypeError,ValueError) as exc:
            raise LocalModelError('Local model output could not be validated.') from exc
        self.last_stats={'cached':False,'wall_seconds':round(monotonic()-start,3),
                         **{k:response.get(k) for k in ('eval_count','eval_duration','prompt_eval_count','load_duration')}}
        # Plain text is escaped before the Telegram HTML renderer sees it.
        rendered=escape(answer.strip())
        if any(len(line)>3000 for line in rendered.splitlines()):
            raise LocalModelError('Generated paragraph is too long for chat display.')
        self.cache[key]=rendered
        if len(self.cache)>32: self.cache.popitem(last=False)
        return rendered


def configured_llm():
    return None if os.getenv('SIGNAL_LLM','on').lower() in ('off','0','false') else OllamaChat()
