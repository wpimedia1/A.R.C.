"""Actual process heartbeat for isolated acceptance runners; no model dispatch."""
from contextlib import contextmanager
import os
import logging
import threading
import time


@contextmanager
def heartbeat(store):
    stop=threading.Event()
    def pulse():
        while not stop.is_set():
            try:store.status('worker',{'heartbeat_at':time.time(),'kind':'isolated-acceptance-runner','process_id':os.getpid(),'error':None})
            except Exception:
                # A failed heartbeat is not replaced by a successful-looking one.
                # Mission receipts/transactions remain owned by the runner itself.
                logging.exception('Acceptance runner heartbeat could not be recorded')
            stop.wait(20)
    thread=threading.Thread(target=pulse,daemon=True);thread.start()
    try:yield
    finally:stop.set();thread.join(timeout=2)
