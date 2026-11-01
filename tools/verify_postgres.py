"""Real pg_dump/pg_restore drill against an isolated database, never over production."""
import json
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def run(*args):
    result=subprocess.run(['docker','compose','exec','-T','database',*args],cwd=ROOT,capture_output=True,text=True,check=True)
    return result.stdout.strip()

def fingerprints(database):
    tables=run('psql','-U','mission','-d',database,'-At','-c',"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
    result={}
    for table in tables:
        if not table.replace('_','').isalnum():raise ValueError('Unexpected table name')
        sql=f'''SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY id),'')) FROM "{table}" t'''
        count,sha=run('psql','-U','mission','-d',database,'-At','-c',sql).split('|')
        result[table]={'rows':int(count),'row_digest_md5':sha}
    return result

def main():
    stamp=str(int(time.time()));restored='mission_restore_'+stamp;dump='/tmp/mission-backup-'+stamp+'.dump'
    # Stop the worker before invoking this drill for a stable comparison.
    before=fingerprints('mission')
    if not before.get('missions',{}).get('rows'):raise RuntimeError('Refusing to call an empty database a successful recovery drill')
    run('pg_dump','-U','mission','-d','mission','-Fc','-f',dump)
    run('createdb','-U','mission',restored)
    try:
        run('pg_restore','-U','mission','-d',restored,'--no-owner','--exit-on-error',dump)
        after=fingerprints(restored)
        report={'checked_at':time.time(),'method':'PostgreSQL custom-format pg_dump restored into a newly created isolated database; row counts and ordered row digests compared for every public table',
                'original_database':'mission','restore_database':restored,'matches':before==after,'before':before,'after':after,
                'backup_file_in_database_container':dump,'original_database_modified':False}
        target=ROOT/'docs'/'postgres-recovery.json';target.write_text(json.dumps(report,indent=2))
        if before!=after:raise RuntimeError('Restored database differs from source; inspect report')
        print(json.dumps({'matches':True,'tables':len(before),'rows':sum(t['rows'] for t in before.values()),'report':str(target)}))
    finally:
        if restored!='mission' and restored.startswith('mission_restore_') and restored[len('mission_restore_'):].isdigit():
            run('dropdb','-U','mission',restored)

if __name__=='__main__':main()
