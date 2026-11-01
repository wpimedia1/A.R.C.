"""Audit submission files and reachable Git blobs without printing secret values."""
import json
import re
import subprocess
import time
from pathlib import Path
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    names=git('ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0')
    files=[ROOT/n for n in names if n and (ROOT/n).is_file()]
    secrets=[v.encode() for k,v in dotenv_values(ROOT/'council-dashboard/backend/.env').items()
             if v and ('KEY' in k or 'TOKEN' in k or 'SECRET' in k) and len(v)>=16]
    oversize=[];hits=[]
    def check(name,raw):
        if any(s in raw for s in secrets):hits.append({'path':name,'reason':'matches a configured credential; value withheld'})
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',raw):hits.append({'path':name,'reason':'private key marker'})
    for p in files:
        size=p.stat().st_size
        if size>=100_000_000:oversize.append({'path':str(p.relative_to(ROOT)),'bytes':size})
        check(str(p.relative_to(ROOT)),p.read_bytes())
    objects=git('rev-list','--objects','--all').splitlines()
    payload=b'\n'.join(line.split(b' ',1)[0] for line in objects)+b'\n'
    meta=subprocess.check_output(['git','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],input=payload,cwd=ROOT)
    largest=0;blob_count=0
    for line in meta.splitlines():
        oid,kind,size=line.decode().split();size=int(size)
        if kind!='blob':continue
        blob_count+=1;largest=max(largest,size)
        if size>=100_000_000:oversize.append({'git_object':oid,'bytes':size})
        check('git:'+oid,git('cat-file','blob',oid))
    report={'checked_at':time.time(),'submission_file_count':len(files),'reachable_blob_count':blob_count,
            'largest_reachable_blob_bytes':largest,'largest_submission_file_bytes':max(p.stat().st_size for p in files),
            'threshold_bytes':100_000_000,'oversized':oversize,'credential_findings':hits,
            'secret_check_scope':'Exact configured credential values and private-key markers in submission files and all reachable Git blobs. Not a claim to detect every possible secret.'}
    (ROOT/'docs/repository-audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
    if oversize or hits:raise SystemExit(1)

if __name__=='__main__':main()
