"""Run the same acceptance tests on isolated SQLite files or PostgreSQL schemas."""
import os
import uuid
from sqlalchemy import create_engine
from mission.store import Store

def make_store(tmp_path,request):
    url=os.getenv('MISSION_TEST_DATABASE_URL')
    if not url:return Store('sqlite:///'+str(tmp_path/'mission.db'))
    schema='test_'+uuid.uuid4().hex
    engine=create_engine(url)
    with engine.begin() as c:c.exec_driver_sql('CREATE SCHEMA '+schema)
    def cleanup():
        with engine.begin() as c:c.exec_driver_sql('DROP SCHEMA '+schema+' CASCADE')
        engine.dispose()
    request.addfinalizer(cleanup)
    store=Store(url+('?options=-csearch_path%3D'+schema))
    request.addfinalizer(store.engine.dispose)
    return store
