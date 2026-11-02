"""Run separately from the API: python -m mission.worker."""
import logging
import time
from .store import Store
from .planner import plan_once, recover_claims, credential_status
from .evidence import refresh, adopt_latest

def site_analysis(store):
    from .media import analyze_site
    try:
        store.status('site-analysis',{'started_at':time.time(),'status':'downloading imagery and segmenting'})
        vid=analyze_site(store)
        store.status('site-analysis',{'finished_at':time.time(),'status':'pinned','version':vid})
        logging.info('Site segmentation pinned as %s',vid)
    except Exception as exc:
        store.status('site-analysis',{'failed_at':time.time(),'error':f'{type(exc).__name__}: {exc}'[:600]})
        logging.exception('Site segmentation failed; recorded, not retried automatically')

_analysis=[None]
_planner=[None]

def planning(store):
    try:plan_once(store)
    except Exception as exc:
        logging.exception('Planning pass failed')
        store.log('worker','error',{'error':f'planning: {type(exc).__name__}: {exc}'[:2000]})

def media_step(store):
    """One media action per loop. SAM site analysis runs beside the loop (the full-resolution image download can take
    minutes and must not hold up DSN reads, planning or ticks); else the next pending illustration."""
    from .media import site_analysis_due, pending_visual, illustrate
    import threading
    if (_analysis[0] is None or not _analysis[0].is_alive()) and site_analysis_due(store):
        _analysis[0]=threading.Thread(target=site_analysis,args=(store,),daemon=True,name='site-analysis');_analysis[0].start()
        return
    trigger=pending_visual(store)
    if trigger:
        record=illustrate(store,'public',trigger)
        if record:logging.info('Illustration %s: %s',trigger,record.get('status'))

def source_refresh(store,started):
    try:
        results=refresh(store);adopt_latest(store)
        from .science import ingest
        try:
            scientific=ingest(store)
            store.status('scientific-refresh',{'checked_at':time.time(),'status':'checked','versions':scientific})
        except Exception as exc:
            store.status('scientific-refresh',{'checked_at':time.time(),'status':'failed; last valid source versions retained','error':f'{type(exc).__name__}: {exc}'[:400]})
            logging.exception('Scientific refresh failed; keeping pinned evidence')
        store.status('source-refresh',{'checked_at':started,'results':results})
        logging.info('Source refresh: %s',results)
    except Exception as exc:
        store.status('source-refresh',{'checked_at':started,'error':f'{type(exc).__name__}: {exc}'[:400]})
        logging.exception('Source refresh failed')


def main():
    logging.basicConfig(level=logging.INFO)
    store=Store()
    from .engine import InvalidAction
    from .package import PackageError
    while True:
        try:
            store.check();break  # never creates the mission: genesis waits for a user to press Start
        except (InvalidAction,PackageError) as exc:
            # Fail loud and stay up: the reason is logged and visible in the API (503) until the operator fixes it.
            store.status('worker',{'heartbeat_at':time.time(),'error':str(exc)})
            logging.error('Mission cannot start: %s',exc);time.sleep(60)
    cleaned=0
    refreshed=(store.status('source-refresh') or {}).get('checked_at',0)
    from .package import load
    from .conditions import poll_dsn
    soi_km=load()['values']['comms.mars_soi_km']
    store.log('worker','started',{'pid':__import__('os').getpid()})
    last_error=[None,0.0,0]
    dsn_polled=0
    refresher=None
    weather_polled=(store.status('weather-feeds') or {}).get('checked_at',0)
    sol_s=load()['values']['mars.sol_s']
    while True:
        try:
            store.status('worker',{'heartbeat_at':time.time(),'credential':credential_status()})
            # Live Mars conditions run whether or not the mission is paused (D10).
            if time.time()-dsn_polled>=60:
                dsn_polled=time.time()
                reading=poll_dsn(store,soi_km)
                if reading.get('error'):logging.warning('DSN Now unavailable: %s',reading['error'])
                elif store.refresh_conditions():logging.info('Live DSN readings applied to the public mission')
            if not store.started():
                # Before Start: only the live DSN reading runs (real observations, recorded). No mission, agents or clock.
                store.status('worker',{'heartbeat_at':time.time(),'credential':credential_status(),'waiting_for':'Start'})
                time.sleep(1);continue
            recover_claims(store)
            # Media first: the genesis illustration is ready within seconds of launch, before the first planning cycle.
            # Measured -> estimated -> checked: NASA weather feeds every 6 h; estimates and checks follow each pull.
            if time.time()-weather_polled>=21600:
                weather_polled=time.time()
                from . import nowcast
                feeds={}
                for station in nowcast.STATIONS:
                    try:
                        new=nowcast.ingest(store,station,nowcast.fetch(station))
                        feeds[station]={'status':'read','new_sols':len(new)}
                    except Exception as exc:
                        feeds[station]={'status':'failed','error':f'{type(exc).__name__}: {exc}'[:400]}
                        logging.warning('Weather feed %s failed: %s',station,feeds[station]['error'])
                try:
                    outcome=nowcast.cycle(store,sol_s)
                    feeds['estimates_made']=len(outcome['estimates']);feeds['checks_made']=len(outcome['checks'])
                    if outcome['checks'] or outcome['estimates']:store.request_replanning('public','New weather measurements or estimates')
                except Exception as exc:
                    feeds['nowcast_error']=f'{type(exc).__name__}: {exc}'[:400];logging.exception('Nowcast failed')
                store.status('weather-feeds',{'checked_at':weather_polled,**feeds})
            media_step(store)
            # Planning makes several model calls (minutes); it runs beside the loop so DSN reads, the heartbeat and other
            # missions' steps continue. A mission under a planning claim is not stepped (store.tick skips it).
            if _planner[0] is None or not _planner[0].is_alive():
                import threading
                _planner[0]=threading.Thread(target=planning,args=(store,),daemon=True,name='planning');_planner[0].start()
            mid=store.tick()
            if mid: logging.info('Committed simulation step for %s',mid)
            cached=store.status('uncertainty') or {}
            public=store.snapshot('public')['state']
            if cached.get('tick') is None or public['tick']-cached['tick']>=24:
                from .schedule import uncertainty
                try:store.status('uncertainty',{**uncertainty(public),'tick':public['tick'],'computed_at':time.time()})
                except Exception as exc:
                    store.status('uncertainty',{'tick':public['tick'],'error':f'{type(exc).__name__}: {exc}'[:400]});logging.exception('Uncertainty forecast failed')
            if time.time()-cleaned>3600: store.cleanup(); cleaned=time.time()
            if time.time()-refreshed>86400 and not (refresher and refresher.is_alive()):
                # Slow downloads (MOLA, SWIM, PDFs) run beside the loop: they never hold up planning or ticks.
                refreshed=time.time()
                import threading
                refresher=threading.Thread(target=source_refresh,args=(store,refreshed),daemon=True,name='source-refresh');refresher.start()
        except Exception as exc:
            logging.exception('Worker step rolled back; retrying after delay')
            message=f'{type(exc).__name__}: {exc}'[:2000]
            # Repeats of the same error are counted, not re-logged every second.
            if message!=last_error[0] or time.time()-last_error[1]>=60:
                try:store.log('worker','error',{'error':message,'repeats_since_last_log':last_error[2]});last_error[:]=[message,time.time(),0]
                except Exception:logging.exception('Event log write failed')
            else:last_error[2]+=1
        time.sleep(1)

if __name__=='__main__': main()
