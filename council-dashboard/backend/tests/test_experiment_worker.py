from copy import deepcopy
import pytest
from conftest import make_store
from mission.experiment_worker import tick_private
from mission.engine import InvalidAction


def test_review_worker_refuses_an_active_public_mission(tmp_path,request):
    store=make_store(tmp_path,request);store.initialize()
    before=store.snapshot('public')
    with pytest.raises(InvalidAction,match='stay paused'):tick_private(store)
    assert store.snapshot('public')==before


def test_private_ticks_keep_public_and_pinned_sources_unchanged(tmp_path,request):
    store=make_store(tmp_path,request);store.initialize()
    with store.transaction()as db:
        m=store.row(db,'public');s=deepcopy(m.state)
        s.update(status='paused',acceptance_scope='explicit unit-test review',review_scope='unit-test only')
        store.save(db,m,s,{'kind':'unit-test-review-setup'})
    public=store.snapshot('public');fork=store.fork(public['revision'],'unit-test-owner')
    assert 'acceptance_scope'not in fork['state'] and 'review_scope'not in fork['state']
    fork=store.control(fork['id'],'unit-test-owner',fork['revision'],'configure',{'planner':'fixed-priority'})
    fork=store.control(fork['id'],'unit-test-owner',fork['revision'],'run',ticks=2)
    for _ in range(3):tick_private(store)
    actual=store.snapshot(fork['id'],'unit-test-owner')
    assert actual['state']['tick']==fork['state']['tick']+2 and actual['queued_ticks']==0
    assert actual['state']['source_pins']==public['state']['source_pins']
    assert store.snapshot('public')==public
