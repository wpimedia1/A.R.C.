"""Local review worker: private bounded experiments with pinned evidence.

No source polling or SAM dispatch. Public review stays paused; the ordinary
mission.worker remains the separately configured public live-operations service.
"""
import logging
import os
import threading
import time
from sqlalchemy import select
from .store import Store,Mission
from .engine import InvalidAction
from .planner import plan_once,recover_claims


def tick_private(store):
    if store.snapshot('public')['state']['status']!='paused':
        raise InvalidAction('The experiment worker requires the public review to stay paused')
    return store.tick()


def plan_private(store):
    try:
        with store.transaction()as db:
            ids=list(db.scalars(select(Mission.id).where(Mission.owner.is_not(None),Mission.pending_ticks>0)))
        for mid in ids:
            if plan_once(store,mission_id=mid):return
    except Exception as exc:
        logging.exception('Private planning failed')
        store.log('worker','error',{'scope':'private-experiments','error':f'{type(exc).__name__}: {exc}'[:1000]})


def main():
    logging.basicConfig(level=logging.INFO)
    store=Store()
    if not str(store.engine.url.database).startswith('mission_review_'):
        raise InvalidAction('This worker is restricted to a separate mission_review_* database')
    store.check()
    if store.snapshot('public')['state']['status']!='paused':raise InvalidAction('Pause the public review first')
    recover_claims(store);planner=None
    store.log('worker','started',{'pid':os.getpid(),'scope':'private-experiments','source_pins_frozen':True})
    while True:
        try:
            if store.snapshot('public')['state']['status']!='paused':raise InvalidAction('Public review was resumed; experiment worker stopped')
            store.status('worker',{'heartbeat_at':time.time(),'pid':os.getpid(),'scope':'private-experiments','source_pins_frozen':True})
            if planner is None or not planner.is_alive():
                planner=threading.Thread(target=plan_private,args=(store,),daemon=True);planner.start()
            mid=tick_private(store)
            if mid:logging.info('Committed private simulation step for %s',mid)
        except Exception as exc:
            store.status('worker',{'heartbeat_at':time.time(),'error':f'{type(exc).__name__}: {exc}'[:1000]})
            logging.exception('Private experiment worker stopped')
            raise
        time.sleep(1)


if __name__=='__main__':main()
