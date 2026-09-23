"""进度事件与任务序列化的新增字段。不连 DB、不连 Redis。"""
import json
from types import SimpleNamespace

from app.modules.crawler.progress_bus import ProgressEvent, TaskProgressBus
from app.modules.crawler.routes import _serialize_task


def test_progress_event_defaults():
    ev = ProgressEvent(task_id="t1", status="running")
    assert ev.tier is None
    assert ev.fallback_done == 0
    assert ev.fallback_total == 0


def test_emit_payload_includes_fallback_fields():
    bus = TaskProgressBus()
    got = []
    bus.subscribe("t1", got.append)
    bus.emit(
        ProgressEvent(
            task_id="t1", status="fallback_running",
            tier="aibrowser", fallback_done=3, fallback_total=7,
        )
    )
    assert len(got) == 1
    payload = json.loads(got[0])
    assert payload["tier"] == "aibrowser"
    assert payload["fallback_done"] == 3
    assert payload["fallback_total"] == 7


def _task(**over):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        task_name="t",
        target_date=None,
        date_to=None,
        url_list=[],
        total_urls=0,
        completed_urls=0,
        failed_urls=0,
        failed_details=None,
        status="running",
        callback_url=None,
        started_at=None,
        completed_at=None,
        created_at=None,
        fallback_total=None,
        fallback_done=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_serialize_task_includes_fallback_counters():
    out = _serialize_task(_task(fallback_total=7, fallback_done=3))
    assert out["fallback_total"] == 7
    assert out["fallback_done"] == 3


def test_serialize_task_coerces_none_to_zero():
    out = _serialize_task(_task())
    assert out["fallback_total"] == 0
    assert out["fallback_done"] == 0
