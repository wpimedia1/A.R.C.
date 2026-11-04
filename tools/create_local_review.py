"""Copy a completed local acceptance into a NEW PostgreSQL review database.

Streams actual rows without ORM receipt hooks, preserving IDs/times rather than
inventing fresh provider events. Never overwrites a nonempty database.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'council-dashboard/backend'))
from mission.store import Base
from sqlalchemy import JSON

CONSUMER=r'''
import sys,json
from copy import deepcopy
from sqlalchemy import select,func
from mission.store import Store,Base
from mission.engine import event
store=Store();counts={}
with store.engine.begin() as connection:
    for table in Base.metadata.sorted_tables:
        if connection.scalar(select(func.count()).select_from(table)):
            raise RuntimeError('Refusing to overwrite nonempty review database')
    for line in sys.stdin:
        item=json.loads(line);table=Base.metadata.tables[item['table']]
        connection.execute(table.insert(),item['row']);counts[table.name]=counts.get(table.name,0)+1
with store.transaction() as db:
    m=store.row(db,'public');s=deepcopy(m.state)
    if s['status']!='paused' or s.get('planning_claim'):raise RuntimeError('Source is not a settled paused experiment')
    s['acceptance_scope']='Local review of the completed real-Meta study with pinned experiment evidence'
    s['review_scope']='Local review copy of the actual completed Meta study; not a fresh provider run'
    event(s,'Local review copy prepared','Actual work, source versions and provider records copied verbatim. Original mission unchanged; public review remains paused.')
    store.save(db,m,s,{'kind':'local-review-copy','provider_calls_dispatched':0,'source_rows_preserved':True})
print(json.dumps({'copied_rows':counts,'review_revision':store.snapshot('public')['revision'],'status':'paused','new_provider_calls':0}))
'''


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--database',required=True)
    p.add_argument('--container',default='meta-hackathon-review-api')
    args=p.parse_args();source=args.source.resolve()
    if not source.is_relative_to((ROOT/'output/live-acceptance').resolve()):p.error('Only isolated acceptance databases are supported')
    if not re.fullmatch(r'mission_review_[a-z0-9_]+',args.database):p.error('Destination must be a separate mission_review_* database')
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)as db:
        state=json.loads(db.execute("SELECT state FROM missions WHERE id='public'").fetchone()[0])
        if state['status']!='paused' or state.get('planning_claim'):raise ValueError('Acceptance must be paused between provider cycles')
        integrity=db.execute('PRAGMA integrity_check').fetchall()
        if integrity!=[('ok',)]:raise ValueError('Source database integrity failed')
        check=subprocess.run(['docker','compose','exec','-T','database','psql','-U','mission','-d','postgres','-At','-c',
            "SELECT 1 FROM pg_database WHERE datname='"+args.database+"'"],cwd=ROOT,capture_output=True,text=True,check=True)
        if not check.stdout.strip():subprocess.run(['docker','compose','exec','-T','database','createdb','-U','mission',args.database],cwd=ROOT,check=True)
        url='postgresql+psycopg://mission:local-development-only@database/'+args.database
        process=subprocess.Popen(['docker','exec','-i','-e','DATABASE_URL='+url,args.container,'python','-c',CONSUMER],
            cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            for table in Base.metadata.sorted_tables:
                cursor=db.execute('SELECT * FROM "'+table.name+'"');names=[x[0]for x in cursor.description]
                json_cols={c.name for c in table.columns if isinstance(c.type,JSON)}
                for values in cursor:
                    row=dict(zip(names,values))
                    if table.name=='service_status' and row['id']=='worker':continue
                    for key in json_cols:
                        if row.get(key)is not None:row[key]=json.loads(row[key])
                    process.stdin.write(json.dumps({'table':table.name,'row':row})+'\n')
            process.stdin.close();process.stdin=None
            out,error=process.communicate()
            if process.returncode:raise RuntimeError(error)
            print(out.strip())
        except BaseException:
            if process.poll()is None:process.terminate()
            raise


if __name__=='__main__':main()
