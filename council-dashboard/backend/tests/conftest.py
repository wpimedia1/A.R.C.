"""Tests run against the real environment package. A temporary copy marks every operator decision
approved so engine behaviour can be exercised; production still requires the owner's approvals."""
import json
import os
import uuid
import tempfile
# mission.api builds its module-level app on import; point it at a throwaway database, never the repo.
# Overrides any DATABASE_URL (e.g. the Docker mission database) so the import never creates a public mission there.
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(prefix='arcadia-tests-'), 'import.db')
import pytest
from sqlalchemy import create_engine
import mission.package as package
from mission.store import Store

REAL_PACKAGES = package.PACKAGES


@pytest.fixture(autouse=True)
def approved_package(tmp_path, monkeypatch):
    pkg = json.loads((REAL_PACKAGES / 'arcadia-mars-v1.json').read_text(encoding='utf-8'))
    for d in pkg['operator_decisions'].values():
        d['approved'] = True
    target = tmp_path / 'packages'
    target.mkdir()
    (target / 'arcadia-mars-v1.json').write_text(json.dumps(pkg), encoding='utf-8')
    for source in REAL_PACKAGES.glob('*.json'):
        if source.name != 'arcadia-mars-v1.json':
            (target / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(package, 'PACKAGES', target)
    monkeypatch.setenv('MISSION_MODEL_MODE', 'fixed-priority')
    return target


def make_store(tmp_path, request):
    url = os.getenv('MISSION_TEST_DATABASE_URL')
    if not url:
        return Store('sqlite:///' + str(tmp_path / 'mission.db'))
    schema = 'test_' + uuid.uuid4().hex
    engine = create_engine(url)
    with engine.begin() as c:
        c.exec_driver_sql('CREATE SCHEMA ' + schema)

    def cleanup():
        with engine.begin() as c:
            c.exec_driver_sql('DROP SCHEMA ' + schema + ' CASCADE')
        engine.dispose()
    request.addfinalizer(cleanup)
    store = Store(url + ('?options=-csearch_path%3D' + schema))
    request.addfinalizer(store.engine.dispose)
    return store
