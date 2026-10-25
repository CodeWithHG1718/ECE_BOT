"""Local, resumable BGE-M3 indexing and hybrid retrieval.

Run from the project root: python ingestion/bge_embeddings.py build
The SQLite index is a rebuildable demo artifact, not the academic source of truth.
"""
import argparse
from contextlib import closing
from collections import Counter, OrderedDict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'datafiles/academic/embedding_chunks.jsonl'
INDEX = ROOT / 'datafiles/academic/vectors/bge-m3.sqlite3'
AZURE_INDEX = ROOT / 'datafiles/academic/vectors/azure-text-embedding-3-small.sqlite3'
MODEL = 'bge-m3:567m'
HF_MODEL = 'BAAI/bge-m3'
HF_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
DIMENSIONS = 1024
AZURE_DIMENSIONS = 1536
CONTEXT = 8192
STOP = set('a an the to of in for and or is are i my me we do does what where should can study learn about please how which who find give help want books book lectures lecture resources resource chapter chapters read covers cover'.split())


def digest(value):
    return hashlib.sha256(value).hexdigest()


def packed(vector, dimensions=DIMENSIONS):
    if len(vector) != dimensions or not all(math.isfinite(x) for x in vector):
        raise ValueError(f'Embedding must have {dimensions} finite dimensions')
    norm = math.sqrt(sum(x*x for x in vector))
    if norm <= 0:
        raise ValueError('Zero embedding returned')
    return struct.pack(f'<{dimensions}f', *(x/norm for x in vector))


def unpacked(blob, dimensions=DIMENSIONS):
    if len(blob)!=dimensions*4:
        raise ValueError(f'Embedding vector must contain {dimensions} float32 values')
    return struct.unpack(f'<{dimensions}f', blob)


def load_environment():
    """Load ignored local .env values without overriding process environment."""
    path=ROOT/'.env'
    if not path.exists(): return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        value=line.strip()
        if not value or value.startswith('#'): continue
        if value.lower().startswith('export '): value=value[7:].lstrip()
        name,separator,content=value.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name.strip()): continue
        content=content.strip()
        if len(content)>=2 and content[0]==content[-1] and content[0] in ('"',"'"):
            content=content[1:-1]
        os.environ.setdefault(name.strip(),content)


def index_for_provider(provider):
    if provider=='azure': return AZURE_INDEX
    if provider in ('huggingface','ollama'): return INDEX
    raise ValueError('Choose the huggingface, ollama or azure embedding provider.')


def configured_embedder(provider=None, download=False):
    load_environment()
    selected=(provider or os.getenv('SIGNAL_EMBEDDING_PROVIDER','huggingface')).strip().lower()
    if selected=='azure': return AzureOpenAIEmbedder()
    if selected=='ollama': return OllamaEmbedder()
    if selected=='huggingface': return HuggingFaceEmbedder(offline=not download)
    raise ValueError('SIGNAL_EMBEDDING_PROVIDER must be huggingface, ollama or azure.')


class OllamaEmbedder:
    """A future provider must implement identity() and encode(list[str])."""
    def __init__(self, base_url='http://127.0.0.1:11434'):
        self.base_url = base_url.rstrip('/')

    def request(self, path, payload=None):
        req = urllib.request.Request(self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Ollama {exc.code}: {exc.read().decode()[:500]}') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError('Ollama is unavailable. Start Ollama and pull bge-m3:567m.') from exc

    def identity(self):
        tags = self.request('/api/tags')['models']
        model = next((m for m in tags if m['name'] == MODEL), None)
        if model is None:
            raise RuntimeError('Model missing. Run: ollama pull bge-m3:567m')
        return {'provider': 'ollama', 'model': MODEL, 'digest': model['digest'],
                'dimensions': DIMENSIONS, 'context': CONTEXT,
                'normalization': 'l2', 'prompt': 'none', 'truncate': False,
                'storage': 'float32-le', 'pipeline_version': 1}

    def encode(self, texts):
        result = self.request('/api/embed', {'model': MODEL, 'input': texts,
            'truncate': False, 'keep_alive': '10m', 'options': {'num_ctx': CONTEXT, 'num_gpu': 99}})
        vectors = result['embeddings']
        if len(vectors) != len(texts):
            raise ValueError('Embedding response count differs from input count')
        return [packed(v) for v in vectors]


class HuggingFaceEmbedder:
    """Pinned original weights; dense CLS embeddings with no query prefix."""
    def __init__(self, offline=True):
        import torch
        from sentence_transformers import SentenceTransformer
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model = SentenceTransformer(HF_MODEL, revision=HF_REVISION,
            cache_folder=str(ROOT/'.cache/huggingface'), device=self.device,
            trust_remote_code=False, local_files_only=offline,
            model_kwargs={'dtype': torch.float32})
        self.model.max_seq_length = CONTEXT
        self.model.eval()
        print(f'BGE-M3 loaded on {self.device} (float32)', flush=True)

    def identity(self):
        return {'provider': 'huggingface', 'model': HF_MODEL, 'revision': HF_REVISION,
            'dimensions': DIMENSIONS, 'context': CONTEXT, 'normalization': 'l2',
            'prompt': 'none', 'truncate': False, 'storage': 'float32-le',
            'compute_dtype': 'float32', 'pipeline_version': 1,
            'sentence_transformers': importlib.metadata.version('sentence-transformers'),
            'transformers': importlib.metadata.version('transformers')}

    def encode(self, texts):
        lengths = [len(ids) for ids in self.model.tokenizer(texts, truncation=False,
            padding=False, add_special_tokens=True)['input_ids']]
        if max(lengths, default=0) > CONTEXT:
            raise ValueError('Chunk exceeds 8192 tokens; split it before embedding. No silent truncation.')
        vectors = self.model.encode(texts, batch_size=min(8,len(texts)),
            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        return [packed(vector.tolist()) for vector in vectors]


class AzureOpenAIEmbedder:
    """Azure OpenAI text-embedding-3-small via the Azure OpenAI v1 endpoint."""
    def __init__(self, endpoint=None, api_key=None, deployment=None, timeout=90):
        load_environment()
        self.endpoint=(endpoint or os.getenv('AZURE_OPENAI_ENDPOINT','')).strip()
        self.api_key=(api_key or os.getenv('AZURE_OPENAI_API_KEY','')).strip()
        self.deployment=(deployment or os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT','')).strip()
        missing=[name for name,value in (
            ('AZURE_OPENAI_ENDPOINT',self.endpoint),
            ('AZURE_OPENAI_API_KEY',self.api_key),
            ('AZURE_OPENAI_EMBEDDING_DEPLOYMENT',self.deployment)) if not value]
        if missing:
            raise RuntimeError('Add '+', '.join(missing)+' to the project .env file. Keep the API key out of chat and source files.')
        parsed=urlsplit(self.endpoint)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port):
            raise ValueError('AZURE_OPENAI_ENDPOINT must be the HTTPS Azure resource endpoint.')
        path=parsed.path.rstrip('/')
        if path not in ('','/openai/v1'):
            raise ValueError('AZURE_OPENAI_ENDPOINT must be the resource root, optionally ending in /openai/v1.')
        self.url=urlunsplit((parsed.scheme,parsed.netloc,'/openai/v1/embeddings','',''))
        self.timeout=timeout
        self.total_input_tokens=0
        self.request_count=0

    def identity(self):
        return {'provider':'azure','model':'text-embedding-3-small',
            'deployment':self.deployment,'model_version':'1','api_version':'v1',
            'dimensions':AZURE_DIMENSIONS,'context':CONTEXT,'normalization':'l2',
            'prompt':'none','truncate':False,'storage':'float32-le',
            'pipeline_version':1}

    def encode(self, texts):
        if not isinstance(texts,(list,tuple)) or not texts:
            raise ValueError('Azure embedding input must be a non-empty list of texts.')
        if len(texts)>2048:
            raise ValueError('Azure allows at most 2,048 text inputs in one embedding request.')
        payload=json.dumps({'model':self.deployment,'input':list(texts),
                            'encoding_format':'float'},ensure_ascii=False).encode('utf-8')
        request=urllib.request.Request(self.url,data=payload,headers={
            'Content-Type':'application/json','api-key':self.api_key},method='POST')
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request,timeout=self.timeout) as response:
                    result=json.load(response)
                break
            except urllib.error.HTTPError as exc:
                body=exc.read().decode('utf-8','replace')[:1000].replace(self.api_key,'[redacted]')
                if exc.code in (429,500,502,503,504) and attempt<4:
                    try: delay=min(30.0,max(1.0,float(exc.headers.get('Retry-After',''))))
                    except (ValueError,TypeError): delay=min(2**attempt,16)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f'Azure embeddings request failed (HTTP {exc.code}): {body}') from None
            except urllib.error.URLError as exc:
                raise RuntimeError('Could not reach the Azure OpenAI embedding endpoint; check the endpoint and network.') from exc
        else:
            raise RuntimeError('Azure embeddings request exhausted retries.')
        try:
            rows=sorted(result['data'],key=lambda row:row['index'])
            vectors=[row['embedding'] for row in rows]
        except (KeyError,TypeError) as exc:
            raise ValueError('Azure returned an invalid embeddings response.') from exc
        if len(vectors)!=len(texts):
            raise ValueError('Azure returned a different number of vectors than input texts.')
        usage=result.get('usage',{})
        self.total_input_tokens+=int(usage.get('prompt_tokens',usage.get('total_tokens',0)) or 0)
        self.request_count+=1
        return [packed(vector,AZURE_DIMENSIONS) for vector in vectors]


def read_chunks(source):
    chunks = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = set()
    for row in chunks:
        if row['chunk_id'] in ids or not row['text'].strip():
            raise ValueError('Duplicate chunk ID or empty text')
        ids.add(row['chunk_id'])
        if not row['metadata'].get('evidence'):
            raise ValueError('Every indexed chunk needs source evidence')
    if not chunks:
        raise ValueError('Refusing to replace index with an empty source')
    return chunks


def open_store(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, vector BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, text TEXT NOT NULL,
            metadata TEXT NOT NULL, vector BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS manifest (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
    ''')
    return db


def build(source=SOURCE, index=None, batch_size=None, embedder=None):
    embedder=embedder or configured_embedder()
    identity=embedder.identity()
    index=index or index_for_provider(identity['provider'])
    if batch_size is None: batch_size=64 if identity['provider']=='azure' else 8
    if batch_size < 1 or batch_size > 64:
        raise ValueError('Batch size must be between 1 and 64')
    chunks = read_chunks(source)
    source_hash = digest(source.read_bytes())
    dimensions=identity['dimensions']
    identity_key = json.dumps(identity, sort_keys=True)
    keys = [digest((identity_key + '\n' + row['text']).encode()) for row in chunks]
    db = open_store(index)
    try:
        existing = {r[0] for r in db.execute('SELECT key FROM cache')}
        pending = list(dict.fromkeys(k for k in keys if k not in existing))
        texts = dict(zip(keys, (r['text'] for r in chunks)))
        print(f'{len(chunks)} chunks; {len(pending)} new unique texts; {len(keys)-len(pending)} reused.', flush=True)
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start+batch_size]
            vectors = embedder.encode([texts[k] for k in batch])
            if len(vectors) != len(batch):
                raise ValueError('Incomplete embedding batch')
            for vector in vectors:
                packed(unpacked(vector,dimensions),dimensions)  # Validate even a replacement provider.
            with db:
                db.executemany('INSERT OR REPLACE INTO cache VALUES (?,?)', zip(batch, vectors))
            print(f'Embedded {min(start+batch_size,len(pending))}/{len(pending)} new texts', flush=True)
        if embedder.identity() != identity:
            raise RuntimeError('Model changed during indexing; old active index retained')
        if digest(source.read_bytes()) != source_hash:
            raise RuntimeError('Source changed during indexing; rerun to publish a consistent index')
        manifest = {'embedding': identity, 'source_sha256': source_hash,
            'chunk_count': len(chunks), 'unique_text_count': len(set(keys)),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'project_demo_staging_not_academic_approval'}
        # Publish only after all batches succeed; interrupted work remains resumable.
        with db:
            db.execute('DELETE FROM documents')
            for row, key in zip(chunks, keys):
                vector = db.execute('SELECT vector FROM cache WHERE key=?', (key,)).fetchone()[0]
                db.execute('INSERT INTO documents VALUES (?,?,?,?)',
                    (row['chunk_id'], row['text'], json.dumps(row['metadata']), vector))
            db.execute('INSERT OR REPLACE INTO manifest VALUES (1,?)', (json.dumps(manifest),))
        print(json.dumps(manifest, indent=2), flush=True)
        return manifest
    finally:
        db.close()


def tokens(text):
    # Light plural normalization aligns filters/filter, signals/signal, circuits/circuit.
    return [t[:-1] if len(t)>4 and t.endswith('s') and not t.endswith(('ss','us','is')) else t
            for t in re.findall(r'[a-z0-9]+', text.lower()) if t not in STOP]


class Retriever:
    def __init__(self, index=None, source=SOURCE, embedder=None):
        load_environment()
        self.embedder=embedder or configured_embedder()
        index=index or index_for_provider(self.embedder.identity()['provider'])
        if not index.exists():
            raise RuntimeError('Build the embedding index first')
        with closing(sqlite3.connect(f'{index.resolve().as_uri()}?mode=ro', uri=True)) as db:
            manifest = db.execute('SELECT value FROM manifest WHERE id=1').fetchone()
            if not manifest:
                raise RuntimeError('Index has not finished building')
            self.manifest = json.loads(manifest[0])
            self.dimensions=self.manifest['embedding']['dimensions']
            records = list(db.execute('SELECT * FROM documents ORDER BY id'))
            self.rows = [{'chunk_id': rid, 'text': text, 'metadata': json.loads(meta),
                          'index': i, 'terms': Counter(tokens(text))}
                         for i,(rid, text, meta, vec) in enumerate(records)]
        try:
            import numpy as np
            self.np = np
            self.matrix = np.frombuffer(b''.join(r[3] for r in records),dtype='<f4').reshape(-1,self.dimensions)
        except ImportError:
            self.np = None
            self.matrix = [unpacked(r[3],self.dimensions) for r in records]
        self.query_cache = OrderedDict()
        self.pool_cache = OrderedDict()
        if self.manifest['source_sha256'] != digest(source.read_bytes()):
            raise RuntimeError('Source changed. Rebuild the embedding index before searching.')
        self.check_model()

    def check_model(self):
        if self.embedder.identity() != self.manifest['embedding']:
            raise RuntimeError('Model/index mismatch. Rebuild all embeddings with the selected model.')

    def search(self, query, course=None, types=None, limit=6, min_dense=0.45):
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ValueError('Query must contain 1 to 1000 characters')
        if not 1 <= limit <= 20:
            raise ValueError('Limit must be between 1 and 20')
        self.check_model()
        pool_key = (course,tuple(sorted(types or [])))
        if pool_key not in self.pool_cache:
            pool = [r for r in self.rows if r['metadata'].get('institute_id') == 'iit-roorkee'
                and (not course or course in r['metadata'].get('curriculum_codes', []))
                and (not types or r['metadata']['document_type'] in types)]
            frequencies = Counter(t for r in pool for t in r['terms'])
            average = sum(sum(r['terms'].values()) for r in pool) / max(1,len(pool)) or 1
            self.pool_cache[pool_key] = (pool,frequencies,average)
            if len(self.pool_cache)>32: self.pool_cache.popitem(last=False)
        self.pool_cache.move_to_end(pool_key)
        pool,frequencies,average = self.pool_cache[pool_key]
        if not pool:
            return []
        query_key = query.strip()
        if query_key not in self.query_cache:
            self.query_cache[query_key] = unpacked(self.embedder.encode([query_key])[0],self.dimensions)
            if len(self.query_cache)>128: self.query_cache.popitem(last=False)
        self.query_cache.move_to_end(query_key)
        qvec = self.query_cache[query_key]
        if self.np is not None:
            dense_scores = self.matrix @ self.np.asarray(qvec,dtype=self.np.float32)
        else:
            dense_scores = [sum(a*b for a,b in zip(qvec,v)) for v in self.matrix]
        words = set(tokens(query))
        scores = []
        for row in pool:
            dense = float(dense_scores[row['index']])
            counts = row['terms']; length = sum(counts.values())
            bm25 = sum(math.log(1+(len(pool)-frequencies[t]+0.5)/(frequencies[t]+0.5))
                * counts[t]*2.2 / (counts[t]+1.2*(0.25+0.75*length/average))
                for t in words if counts[t])
            scores.append({'row': row, 'dense': dense, 'lexical': bm25, 'rrf': 0.0})
        # Rank fusion avoids treating cosine and BM25 as comparable scales.
        for field in ('dense', 'lexical'):
            ranked = sorted((s for s in scores if field=='dense' or s[field]>0), key=lambda s:-s[field])[:50]
            for rank, result in enumerate(ranked, 1):
                result['rrf'] += 1/(60+rank)
        results = []; seen = set()
        for score in sorted(scores, key=lambda s:(-s['rrf'], -s['dense'])):
            if score['dense'] < min_dense or score['rrf'] == 0:
                continue
            row = score['row']; meta = row['metadata']
            entity = (meta['document_type'], meta['entity_id'])
            if entity in seen:
                continue
            seen.add(entity)
            results.append({'chunk_id': row['chunk_id'], 'text': row['text'], 'metadata': meta,
                'scores': {k:round(score[k],6) for k in ('dense','lexical','rrf')}})
            if len(results) >= limit:
                break
        return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    builder = sub.add_parser('build')
    builder.add_argument('--batch-size', type=int)
    builder.add_argument('--download', action='store_true', help='Allow initial Hugging Face download')
    builder.add_argument('--provider', choices=['huggingface','ollama','azure'])
    query = sub.add_parser('search')
    query.add_argument('query'); query.add_argument('--course')
    query.add_argument('--type', action='append', dest='types')
    query.add_argument('--limit', type=int, default=6)
    query.add_argument('--provider', choices=['huggingface','ollama','azure'])
    args = parser.parse_args()
    load_environment()
    embedder=configured_embedder(args.provider,getattr(args,'download',False))
    index=index_for_provider(embedder.identity()['provider'])
    if args.command == 'build':
        build(index=index,batch_size=args.batch_size,embedder=embedder)
    else:
        print(json.dumps(Retriever(index=index,embedder=embedder).search(
            args.query,args.course,args.types,args.limit),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
