from __future__ import annotations

import hashlib
import json
import math
from typing import Callable

from sqlalchemy import delete, insert, select, text as sql_text, update
from sqlalchemy.engine import Engine

from .config import Settings, get_settings
from .db import index_versions, source_chunks, source_embedding_vectors, now_kolkata

NORMALIZATION = 'l2'
Embedder = Callable[[list[str], Settings], tuple[list[list[float]], str]]


class IndexConfigurationError(RuntimeError):
    pass


def _identity(settings: Settings) -> tuple[str, str, str | None]:
    provider = settings.embedding_provider.casefold().strip()
    if provider == 'openai':
        return provider, settings.openai_embedding_model, settings.resolved_openai_embedding_api_key
    if provider == 'azure':
        configured = bool(settings.azure_openai_api_key and settings.azure_openai_endpoint and
                          settings.azure_openai_embedding_deployment and settings.azure_openai_api_version)
        return provider, settings.azure_openai_embedding_deployment or '', settings.azure_openai_api_key if configured else None
    raise IndexConfigurationError('Only the explicitly configured OpenAI or Azure embedding provider is supported.')


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if not vector or not math.isfinite(norm) or norm == 0:
        raise IndexConfigurationError('Embedding response has an invalid vector.')
    return [float(value) / norm for value in vector]


def embed_texts(texts: list[str], settings: Settings) -> tuple[list[list[float]], str]:
    provider, model, key = _identity(settings)
    if not key or not model:
        raise IndexConfigurationError('Embedding credentials and model deployment are not configured.')
    client = None
    try:
        from openai import OpenAI, AzureOpenAI
        if provider == 'openai':
            client = OpenAI(api_key=key)
            response = client.embeddings.create(model=model, input=texts)
        else:
            client = AzureOpenAI(api_key=key, azure_endpoint=settings.azure_openai_endpoint,
                                 api_version=settings.azure_openai_api_version)
            response = client.embeddings.create(model=model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [[float(x) for x in item.embedding] for item in ordered], response.model or model
    finally:
        if client is not None:
            client.close()


def _manifest_id(provider: str, model: str, model_version: str, dimensions: int, normalization: str = NORMALIZATION) -> str:
    identity = '\0'.join((provider, model, model_version, str(dimensions), normalization))
    return hashlib.sha256(identity.encode()).hexdigest()


def build_index(engine: Engine, batch_size: int = 64, settings: Settings | None = None,
                embedder: Embedder | None = None) -> dict:
    """Build one complete index atomically for the selected provider/model identity."""
    settings = settings or get_settings()
    provider, model, key = _identity(settings)
    if not key and embedder is None:
        raise IndexConfigurationError('Embedding credentials are not configured for the selected provider.')
    if not 1 <= batch_size <= 128:
        raise IndexConfigurationError('batch_size must be between 1 and 128.')
    # Seed normalized source records and chunks before embedding.
    from .data import load_dataset
    load_dataset(engine)
    with engine.connect() as conn:
        chunks = conn.execute(select(source_chunks.c.id, source_chunks.c.text).order_by(source_chunks.c.id)).all()
    if not chunks:
        raise IndexConfigurationError('No provenance-backed source chunks are available to index.')
    embed = embedder or embed_texts
    vectors: list[list[float]] = []
    model_version = None
    for offset in range(0, len(chunks), batch_size):
        batch = [row.text for row in chunks[offset:offset + batch_size]]
        batch_vectors, batch_version = embed(batch, settings)
        if len(batch_vectors) != len(batch):
            raise IndexConfigurationError('Embedding provider returned an incomplete batch.')
        if model_version is not None and model_version != batch_version:
            raise IndexConfigurationError('Embedding provider changed model identity during index build.')
        model_version = batch_version
        vectors.extend(batch_vectors)
    dimensions = len(vectors[0])
    if not dimensions or any(len(vector) != dimensions for vector in vectors):
        raise IndexConfigurationError('Embedding provider returned inconsistent vector dimensions.')
    if engine.dialect.name == 'postgresql' and dimensions > 2000:
        raise IndexConfigurationError('The PostgreSQL pgvector HNSW index supports at most 2000 dimensions here.')
    normalized = [_normalize(vector) for vector in vectors]
    model_version = model_version or model
    version_id = _manifest_id(provider, model, model_version, dimensions)
    now = now_kolkata()
    with engine.begin() as conn:
        manifest = conn.execute(select(index_versions.c.id).where(index_versions.c.id == version_id)).first()
        if manifest is None:
            conn.execute(insert(index_versions).values(id=version_id, provider=provider, model=model,
                model_version=model_version, dimensions=dimensions, normalization=NORMALIZATION,
                complete=False, created_at=now))
        else:
            conn.execute(update(index_versions).where(index_versions.c.id == version_id).values(complete=False, created_at=now))
        conn.execute(delete(source_embedding_vectors).where(source_embedding_vectors.c.index_version_id == version_id))
        rows = [{'chunk_id': row.id, 'index_version_id': version_id, 'embedding_json': vector}
                for row, vector in zip(chunks, normalized, strict=True)]
        if engine.dialect.name == 'postgresql':
            stmt = sql_text("""INSERT INTO source_embedding_vectors
                (chunk_id, index_version_id, embedding_json, embedding)
                VALUES (:chunk_id, :index_version_id, CAST(:embedding_json AS jsonb), CAST(:embedding AS vector))""")
            conn.execute(stmt, [{'chunk_id': r['chunk_id'], 'index_version_id': version_id,
                                 'embedding_json': json.dumps(r['embedding_json']),
                                 'embedding': '[' + ','.join(format(x, '.9g') for x in r['embedding_json']) + ']'} for r in rows])
        else:
            conn.execute(insert(source_embedding_vectors), rows)
        count = conn.execute(select(source_embedding_vectors.c.chunk_id).where(source_embedding_vectors.c.index_version_id == version_id)).all()
        if len(count) != len(chunks):
            raise IndexConfigurationError('Index build did not cover every source chunk; transaction rolled back.')
        if engine.dialect.name == 'postgresql':
            # A partial index per manifest keeps providers/models/dimensions physically isolated.
            index_name = f'source_embedding_vectors_hnsw_{version_id[:16]}'
            conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {index_name} ON source_embedding_vectors USING hnsw ((embedding::vector({dimensions})) vector_cosine_ops) WHERE index_version_id = '{version_id}'")
        conn.execute(update(index_versions).where(index_versions.c.id == version_id).values(complete=True))
    return {'index_version_id': version_id, 'provider': provider, 'model': model,
            'model_version': model_version, 'dimensions': dimensions, 'normalization': NORMALIZATION,
            'chunk_count': len(chunks), 'complete': True}


def dense_search(engine: Engine, query: str, limit: int, settings: Settings | None = None,
                 embedder: Embedder | None = None) -> tuple[list[dict], str]:
    settings = settings or get_settings()
    try:
        provider, model, key = _identity(settings)
    except IndexConfigurationError:
        return [], 'provider_unsupported'
    if not key and embedder is None:
        return [], 'credentials_missing'
    with engine.connect() as conn:
        candidates = conn.execute(select(index_versions).where(
            index_versions.c.provider == provider, index_versions.c.model == model,
            index_versions.c.normalization == NORMALIZATION, index_versions.c.complete.is_(True)
        ).order_by(index_versions.c.created_at.desc())).mappings().all()
    if not candidates:
        return [], 'index_incomplete'
    embed = embedder or embed_texts
    try:
        vectors, model_version = embed([query], settings)
        if len(vectors) != 1:
            return [], 'embedding_response_invalid'
        vector = _normalize(vectors[0])
    except Exception:
        # No provider errors or credentials are surfaced; keyword retrieval remains available.
        return [], 'embedding_unavailable'
    dimensions = len(vector)
    matching = [row for row in candidates if row['model_version'] == model_version and row['dimensions'] == dimensions]
    if not matching:
        return [], 'manifest_mismatch'
    manifest = matching[0]
    if engine.dialect.name == 'postgresql':
        literal = '[' + ','.join(format(x, '.9g') for x in vector) + ']'
        version_id = manifest['id']
        try:
            with engine.connect() as conn:
                rows = conn.execute(sql_text(f"""SELECT c.id, c.text, c.metadata,
                    1 - ((e.embedding::vector({dimensions})) <=> CAST(:embedding AS vector({dimensions}))) AS score
                    FROM source_embedding_vectors e JOIN source_chunks c ON c.id=e.chunk_id
                    WHERE e.index_version_id='{version_id}'
                    ORDER BY (e.embedding::vector({dimensions})) <=> CAST(:embedding AS vector({dimensions})) LIMIT :limit"""),
                    {'embedding': literal, 'limit': limit}).mappings().all()
            return [dict(r, chunk_id=r['id'], score=float(r['score'])) for r in rows], 'ready'
        except Exception:
            return [], 'vector_query_unavailable'
    with engine.connect() as conn:
        rows = conn.execute(select(source_embedding_vectors.c.chunk_id, source_embedding_vectors.c.embedding_json,
                                   source_chunks.c.text, source_chunks.c.metadata)
            .join(source_chunks, source_chunks.c.id == source_embedding_vectors.c.chunk_id)
            .where(source_embedding_vectors.c.index_version_id == manifest['id'])).mappings().all()
    scored = []
    for row in rows:
        candidate = row['embedding_json']
        if not isinstance(candidate, list) or len(candidate) != dimensions:
            continue
        similarity = sum(a * float(b) for a, b in zip(vector, candidate, strict=True))
        scored.append({'id': row['chunk_id'], 'chunk_id': row['chunk_id'], 'text': row['text'],
                       'metadata': row['metadata'], 'score': similarity})
    scored.sort(key=lambda item: item['score'], reverse=True)
    return scored[:limit], 'ready'


def reciprocal_rank_fusion(keyword_rows: list[dict], dense_rows: list[dict], limit: int, k: int = 60) -> list[dict]:
    merged: dict[str, dict] = {}
    for source, rows in (('keyword', keyword_rows), ('dense', dense_rows)):
        for rank, item in enumerate(rows, start=1):
            chunk_id = item.get('chunk_id') or item.get('id')
            if not chunk_id:
                continue
            current = merged.setdefault(chunk_id, {**item, 'chunk_id': chunk_id, 'score': 0.0, 'retrieval_sources': []})
            current['score'] += 1.0 / (k + rank)
            current['retrieval_sources'].append(source)
            if source == 'dense':
                current['dense_score'] = item.get('score')
            else:
                current['keyword_score'] = item.get('score')
    return sorted(merged.values(), key=lambda item: item['score'], reverse=True)[:limit]
