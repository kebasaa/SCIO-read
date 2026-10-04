"""Run the unchanged campaign with SQLite WAL to permit concurrent progress reads.

No changes to key/configuration/evaluation logic or the immutable manifest.
Only local checkpoint connection settings are changed.
"""
import runpy
import json
import sqlite3
import sys
import _bootstrap
from scio_offline import bounded_campaign

original_connect=sqlite3.connect
original_run_jobs=bounded_campaign.run_jobs


def run_jobs(directory, manifest, jobs, blobs, **kwargs):
    # JSON stores configuration tuples as lists. Normalize only representation,
    # not values, before the unchanged executor's exact manifest comparison.
    manifest=json.loads(json.dumps(manifest))
    return original_run_jobs(directory,manifest,jobs,blobs,**kwargs)


def connect(database, *args, **kwargs):
    kwargs.setdefault('timeout',30)
    db=original_connect(database,*args,**kwargs)
    if str(database).endswith('results.sqlite'):
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=30000')
    return db


if __name__=='__main__':
    sqlite3.connect=connect
    bounded_campaign.run_jobs=run_jobs
    sys.argv[0]='dev/scripts/bounded_identity_campaign.py'
    runpy.run_path(sys.argv[0],run_name='__main__')
