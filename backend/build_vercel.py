"""Bundle the existing academic records and initialize the deployment database."""
import shutil
import os
from pathlib import Path

SERVICE = Path(__file__).resolve().parent
SOURCE = SERVICE.parent / 'datafiles' / 'academic'
TARGET = SERVICE / 'datafiles' / 'academic'


def bundle():
    from app.data import FILES
    TARGET.mkdir(parents=True, exist_ok=True)
    names = set(FILES.values()) | {'optional_course_catalogue.json', 'local_source_manifest.json',
                                  'web_source_manifest.json', 'embedding_chunks.jsonl'}
    for name in sorted(names):
        source = SOURCE / name
        if not source.is_file():
            raise RuntimeError(f'Missing academic build input: {name}')
        shutil.copy2(source, TARGET / name)


def initialize():
    # Import after bundling so the shared loader selects the packaged data directory.
    from app import data
    from app.db import make_engine
    from sqlalchemy import text
    data.DATA = TARGET
    engine = make_engine(os.environ.get('DATABASE_URL_UNPOOLED') or os.environ.get('POSTGRES_URL_NON_POOLING'))
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Set the deployment DATABASE_URL to a PostgreSQL database before building.')
    try:
        with engine.connect() as guard:
            guard.execute(text('SELECT pg_advisory_lock(517202601)'))
            try:
                data.load_dataset(engine)
            finally:
                guard.execute(text('SELECT pg_advisory_unlock(517202601)'))
    finally:
        engine.dispose()


if __name__ == '__main__':
    print('Bundling academic data...', flush=True)
    bundle()
    print('Initializing deployment database...', flush=True)
    initialize()
    print('Academic data bundled and deployment database initialized.')
