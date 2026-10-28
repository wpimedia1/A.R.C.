"""Run separately from the API: python -m mission.worker."""
import logging
import time
from .store import Store
from .planner import plan_once, recover_claims
from .evidence import refresh, adopt_latest

def main():
    logging.basicConfig(level=logging.INFO)
    store=Store(); store.initialize()
    cleaned=0
    refreshed=(store.status('source-refresh') or {}).get('checked_at',0)
    while True:
        try:
            store.status('worker',{'heartbeat_at':time.time()})
            recover_claims(store)
            plan_once(store)
            mid=store.tick()
            if mid: logging.info('Committed simulation step for %s',mid)
            if time.time()-cleaned>3600: store.cleanup(); cleaned=time.time()
            if time.time()-refreshed>86400:
                results=refresh(store);adopt_latest(store);refreshed=time.time()
                store.status('source-refresh',{'checked_at':refreshed,'results':results})
                logging.info('Source refresh: %s',results)
        except Exception:
            logging.exception('Worker step rolled back; retrying after delay')
        time.sleep(1)

if __name__=='__main__': main()
