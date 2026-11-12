"""Explicit migration command. No automatic migrations during application startup."""
import argparse
import os
from pathlib import Path
import psycopg

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true',help='Apply 001_admin.sql to DATABASE_URL')
    args=parser.parse_args()
    if not args.apply:
        parser.error('Explicit --apply required. Check target DATABASE_URL first.')
    if not os.getenv('DATABASE_URL'):
        raise SystemExit('DATABASE_URL is required')
    try:
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,connect_timeout=5) as conn:
            conn.execute(Path(__file__).resolve().parents[1].joinpath('migrations/001_admin.sql').read_text())
    except Exception:
        raise SystemExit('Migration failed. Database details omitted.') from None
    print('Migration 001_admin applied')
