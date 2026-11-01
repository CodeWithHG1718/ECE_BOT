-- Additive upgrade for databases that already applied the first backend schema.
-- Legacy ties use user before assistant, then ID; timestamps cannot recover other order.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sequence integer NOT NULL DEFAULT 0;
UPDATE messages AS current_message
SET sequence = (
  SELECT COUNT(*) FROM messages AS prior_message
  WHERE prior_message.conversation_id = current_message.conversation_id
    AND (prior_message.created_at < current_message.created_at
      OR (prior_message.created_at = current_message.created_at AND (
        CASE prior_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
          < CASE current_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
        OR (CASE prior_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
          = CASE current_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
          AND prior_message.id <= current_message.id)
      ))
)
)
WHERE sequence = 0;
CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_sequence_uq ON messages(conversation_id, sequence);

CREATE TABLE IF NOT EXISTS source_chunk_documents (
  chunk_id varchar(96) NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
  document_id varchar(96) NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  PRIMARY KEY(chunk_id, document_id)
);
ALTER TABLE source_chunks ADD COLUMN IF NOT EXISTS search_document tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED;
CREATE INDEX IF NOT EXISTS source_chunks_search_document_gin ON source_chunks USING GIN(search_document);
CREATE TABLE IF NOT EXISTS source_embedding_vectors (
  chunk_id varchar(96) NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
  index_version_id varchar(96) NOT NULL REFERENCES index_versions(id) ON DELETE CASCADE,
  embedding_json jsonb NOT NULL,
  embedding vector,
  PRIMARY KEY(chunk_id, index_version_id)
);
ALTER TABLE source_embedding_vectors ADD COLUMN IF NOT EXISTS embedding vector;
CREATE INDEX IF NOT EXISTS source_embedding_vectors_version_idx ON source_embedding_vectors(index_version_id, chunk_id);
