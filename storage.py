"""Shared PostgreSQL on Vercel; SQLite is available only for local development."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
class ConfigurationError(RuntimeError):
    pass

class Connection:
    def __init__(self, raw, postgres):
        self.raw, self.postgres = raw, postgres
    def execute(self, sql, args=()):
        return self.raw.execute(sql.replace('?', '%s') if self.postgres else sql, args)

@contextmanager
def database():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        if not url.startswith(('postgres://', 'postgresql://')):
            raise ConfigurationError('DATABASE_URL must be a PostgreSQL connection URL.')
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None, client_encoding='utf8')
    else:
        if os.environ.get('VERCEL'):
            raise ConfigurationError('Set DATABASE_URL to a persistent PostgreSQL database before using the app on Vercel.')
        path = Path(os.environ.get('LOCAL_DATABASE_PATH', str(ROOT/'data'/'local.sqlite3')))
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, timeout=15)
        raw.row_factory = sqlite3.Row
        raw.execute('PRAGMA foreign_keys=ON')
    try:
        yield Connection(raw, bool(url))
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()

def initialize():
    with database() as db:
        for statement in (ROOT/'schema.sql').read_text().split(';'):
            if statement.strip():
                db.execute(statement)

if __name__ == '__main__':
    initialize()
    print('Database schema is ready. No existing students or progress were deleted.')
