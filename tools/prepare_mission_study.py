"""Create a NEW specification study with actual pinned evidence, never migrate results.

This preserves old acceptance outcomes and does not import any inference receipts.
The well reserve/feed choices are explicitly the new specification's D21 assumptions.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'council-dashboard/backend'))
from mission.store import Store,SourceVersion
from mission.engine import apply_environment,event
from mission.science import ingest_well_reference
from mission.spec import digest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True,help='Actual previously exported evidence/snapshot bundle')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();bundle=json.loads(args.source.read_text(encoding='utf-8-sig'))
    folder=ROOT/'output/mission-studies';folder.mkdir(parents=True,exist_ok=True)
    path=Path(tempfile.mkdtemp(prefix='study-',dir=folder))/'mission.db'
    store=Store('sqlite:///'+path.as_posix());store.initialize()
    reference=ingest_well_reference(store)  # actual NASA retrieval and passage verification
    with store.transaction() as db:
        for key,vid in bundle['snapshot']['state']['source_pins'].items():
            record=bundle['source_versions'].get(vid)
            if not record or record.get('source_id',key)!=key:raise ValueError('Missing or mismatched pinned source '+vid)
            if not db.get(SourceVersion,vid):db.add(SourceVersion(id=vid,source_id=key,record=deepcopy(record)))
        m=store.row(db,'public');s=deepcopy(m.state);package=s['spec']['package_id']
        s['source_pins'].update({k:v for k,v in bundle['snapshot']['state']['source_pins'].items()if k!=package})
        s['source_pins']['hoffman2018']=reference
        prior=bundle['snapshot']['state']
        if prior.get('environment'):apply_environment(s,deepcopy(prior['environment']))
        if prior.get('local_sensors') is not None:s['local_sensors']=deepcopy(prior['local_sensors'])
        s.update(status='paused',mode='meta',planning_needed=True,inference_stopped=False)
        event(s,'New specification study','Fresh simulation state with exact prior evidence pins and new D21 model assumptions. No prior work outcomes or provider receipts imported.')
        store.save(db,m,s,{'kind':'new-specification-study','prior_input_hash':digest(bundle['snapshot']['state']),
                          'physical_state_imported':False,'provider_receipts_imported':False,'source_bundle_hash':digest(bundle)})
    snapshot=store.snapshot('public');exported=store.export('public')
    result={'snapshot':snapshot,'source_versions':exported['source_versions'],
            'basis':'Fresh explicitly versioned study; pinned observations retained, model state reinitialized without importing prior outcomes',
            'database':str(path)}
    args.out.write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps({'database':str(path),'output':str(args.out),'engine':snapshot['state']['spec']['version'],
                      'reserve_kg':snapshot['state']['well']['reserve_kg'],'provider_requests':0,'evidence_pins':len(snapshot['state']['source_pins'])}))


if __name__=='__main__':main()
