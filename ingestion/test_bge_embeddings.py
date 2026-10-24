"""Offline integrity tests. Fake vectors test mechanics, not model quality."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from bge_embeddings import build, Retriever, packed, DIMENSIONS


class FakeEmbedder:
    def __init__(self):
        self.calls = 0
        self.version = 'test-v1'
        self.fail = False

    def identity(self):
        return {'model': 'fake-test-only', 'digest': self.version}

    def encode(self, texts):
        self.calls += len(texts)
        if self.fail:
            raise RuntimeError('Simulated failure')
        return [packed([1.0] + [0.0]*(DIMENSIONS-1)) for text in texts]


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'chunks.jsonl'
        self.index = self.root/'index.sqlite3'
        self.model = FakeEmbedder()
        self.rows = [self.row('1', 'convolution signals', 'ECC-106'), self.row('2', 'electromagnetic fields', 'ECC-203')]
        self.save()

    def row(self, id, text, code):
        return {'chunk_id': id, 'text': text, 'metadata': {'institute_id': 'iit-roorkee',
            'document_type': 'book_chapter', 'entity_id': id, 'curriculum_codes': [code],
            'evidence': [{'url': 'https://example.org/source'}]}}

    def save(self):
        self.source.write_text('\n'.join(json.dumps(r) for r in self.rows), encoding='utf-8')

    def build(self):
        return build(self.source, self.index, batch_size=1, embedder=self.model)

    def reader(self):
        return Retriever(self.index, self.source, self.model)

    def test_rerun_and_metadata_changes_reuse_vectors(self):
        self.build(); self.assertEqual(self.model.calls, 2)
        self.rows[0]['metadata']['extra'] = 'updated citation'
        self.save(); self.build()
        self.assertEqual(self.model.calls, 2)
        self.assertEqual(self.reader().rows[0]['metadata']['extra'], 'updated citation')

    def test_content_and_model_changes_reembed(self):
        self.build()
        self.rows[0]['text'] = 'updated convolution'
        self.save(); self.build(); self.assertEqual(self.model.calls, 3)
        self.model.version = 'test-v2'
        with self.assertRaisesRegex(RuntimeError, 'mismatch'): self.reader()
        self.build(); self.assertEqual(self.model.calls, 5)

    def test_stale_source_is_refused_and_removed_chunks_disappear(self):
        self.build(); self.rows.pop(); self.save()
        with self.assertRaisesRegex(RuntimeError, 'Source changed'): self.reader()
        self.build(); self.assertEqual(len(self.reader().rows), 1)

    def test_failure_retains_published_snapshot(self):
        self.build()
        self.rows.append(self.row('3', 'new topic', 'ECC-104')); self.save()
        self.model.fail = True
        with self.assertRaises(RuntimeError): self.build()
        with closing(sqlite3.connect(self.index)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 2)
        self.model.fail = False
        self.build(); self.assertEqual(len(self.reader().rows), 3)

    def test_filters_and_evidence_survive_retrieval(self):
        self.build()
        hits = self.reader().search('convolution', 'ECC-106', ['book_chapter'])
        self.assertEqual([h['metadata']['entity_id'] for h in hits], ['1'])
        self.assertTrue(hits[0]['metadata']['evidence'])
        self.assertEqual(self.reader().search('convolution', 'ECC-999'), [])

    def test_invalid_vectors_and_inputs_are_rejected(self):
        for vector in ([1.0], [float('nan')]*DIMENSIONS, [0.0]*DIMENSIONS):
            with self.assertRaises(ValueError): packed(vector)
        self.rows.append(self.rows[0]); self.save()
        with self.assertRaises(ValueError): self.build()

    def test_repeated_queries_reuse_embedding_but_keep_filtering(self):
        self.build(); retriever=self.reader(); before=self.model.calls
        first=retriever.search('convolution','ECC-106')
        second=retriever.search('convolution','ECC-203')
        self.assertEqual(self.model.calls,before+1)
        self.assertNotEqual(first[0]['metadata']['entity_id'],second[0]['metadata']['entity_id'])


if __name__ == '__main__':
    unittest.main()
