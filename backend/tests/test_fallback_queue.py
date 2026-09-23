"""兜底队列的分类、终态判定与消费循环。不连 DB、不装 browser-use。"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.crawler import service


class TestClassifyResult:
    """归类必须与原 `run_crawl_job` 里的 if/elif 链逐条一致（spec §12 验收 1）。

    原链是**先判 `ok`、再判 dedup/filtered**（`backend/app/modules/crawler/service.py:372-379`），
    所以 `{"ok": True, "dedup": True}` 算 completed。不要"顺手修"成 filtered —— 那会改变
    开关关闭时的计数口径，破坏验收 1 要求的逐字节一致。
    """

    def test_ok_is_done(self):
        assert service.classify_result({"ok": True, "article_id": "x"}) == "done"

    def test_dedup_with_ok_is_done(self):
        assert service.classify_result({"ok": True, "dedup": True}) == "done"

    def test_filtered_with_ok_is_done(self):
        assert service.classify_result({"ok": True, "filtered": True}) == "done"

    def test_dedup_without_ok_is_filtered(self):
        assert service.classify_result({"ok": False, "dedup": True}) == "filtered"

    def test_filtered_without_ok_is_filtered(self):
        assert service.classify_result({"ok": False, "filtered": True}) == "filtered"

    def test_fallback_marker(self):
        assert service.classify_result({"ok": False, "fallback": True}) == "fallback"

    def test_direct_fallback_marker(self):
        assert service.classify_result({"ok": False, "direct_fallback": True}) == "fallback"

    def test_plain_failure(self):
        assert service.classify_result({"ok": False, "code": 2001}) == "failed"

    def test_exception_is_failed(self):
        assert service.classify_result(RuntimeError("boom")) == "failed"

    def test_none_is_failed(self):
        assert service.classify_result(None) == "failed"


class TestSettleStatus:
    def test_all_filtered(self):
        assert service.settle_status(completed=0, failed=0, filtered=3) == "partial_failed"

    def test_no_failures(self):
        assert service.settle_status(completed=2, failed=0, filtered=0) == "completed"

    def test_no_successes(self):
        assert service.settle_status(completed=0, failed=2, filtered=0) == "failed"

    def test_mixed(self):
        assert service.settle_status(completed=1, failed=1, filtered=0) == "partial_failed"

    def test_fallback_failures_count_as_failures(self):
        """兜底也失败 → 终态 failed，与常规失败同等对待。"""
        assert service.settle_status(completed=0, failed=1, filtered=0) == "failed"


class TestFallbackMarkOk:
    def test_article_id_means_ok(self):
        assert service.fallback_mark_ok("abc") is True

    def test_none_means_not_ok(self):
        assert service.fallback_mark_ok(None) is False


@pytest.mark.asyncio
async def test_drain_counts_success_and_failure():
    claimed = [("row-1", "https://a.com/1"), ("row-2", "https://b.com/2")]
    browse = AsyncMock(side_effect=[
        {"ok": True, "title": "T1", "content": "x" * 200},
        {"ok": False, "reason": "agent failed"},
    ])
    store = AsyncMock(return_value="article-1")
    mark = AsyncMock()
    rec_ab = MagicMock()  # record_ab_result 是同步方法（记忆层 Task 6），不是 async

    with patch.object(service, "_claim_fallback_batch", AsyncMock(return_value=claimed)), \
         patch.object(service, "_mark_fallback_progress", mark), \
         patch.object(service, "_store_ai_browsed_article", store), \
         patch("app.modules.crawler.ai_browser.browse_with_ai", browse), \
         patch("app.modules.crawler.ai_browser.load_ai_browser_config",
               AsyncMock(return_value={"api_key": "k", "base_url": "b", "model": "m"})), \
         patch("app.modules.crawler.service.renderer") as fake_renderer:
        fake_renderer.record_ab_result = rec_ab
        ok, fail = await service._drain_fallback_queue("t1", target_date=date(2026, 9, 23))

    assert (ok, fail) == (1, 1)
    assert rec_ab.call_count == 2
    assert rec_ab.call_args_list[0].args == ("https://a.com/1", True)
    assert rec_ab.call_args_list[1].args == ("https://b.com/2", False)
    # 失败项被登记，成功项不登记
    assert mark.await_count == 2
    assert mark.await_args_list[1].kwargs["failed_ids"] == [("row-2", service.FALLBACK_FAIL_REASON)]


@pytest.mark.asyncio
async def test_drain_stops_on_cancel():
    claimed = [("row-1", "https://a.com/1"), ("row-2", "https://b.com/2")]
    service._cancelled_tasks.add("t-cancel")
    browse = AsyncMock(return_value={"ok": True, "title": "T", "content": "x" * 200})
    try:
        with patch.object(service, "_claim_fallback_batch", AsyncMock(return_value=claimed)), \
             patch.object(service, "_mark_fallback_progress", AsyncMock()), \
             patch.object(service, "_store_ai_browsed_article", AsyncMock(return_value="a1")), \
             patch("app.modules.crawler.ai_browser.browse_with_ai", browse), \
             patch("app.modules.crawler.ai_browser.load_ai_browser_config",
                   AsyncMock(return_value={"api_key": "k", "base_url": "b", "model": "m"})), \
             patch("app.modules.crawler.service.renderer") as fake_renderer:
            fake_renderer.record_ab_result = MagicMock()
            ok, fail = await service._drain_fallback_queue("t-cancel", target_date=date(2026, 9, 23))
    finally:
        service._cancelled_tasks.discard("t-cancel")

    assert ok == 0
    assert browse.await_count == 0


@pytest.mark.asyncio
async def test_drain_empty_queue_returns_zeros():
    with patch.object(service, "_claim_fallback_batch", AsyncMock(return_value=[])):
        assert await service._drain_fallback_queue("t1", target_date=date(2026, 9, 23)) == (0, 0)


@pytest.mark.asyncio
async def test_settle_after_fallback_counts_and_settles_status():
    """2 成 1 败：成功数补进 completed_urls、失败数补进 failed_urls，终态按既有规则算成 partial_failed。

    这是 `_settle_after_fallback` 唯一一条覆盖用例——它管的是「兜底结果如何落回计数器」，
    主循环里被标记 fallback 的 URL 既不在 completed_urls 也不在 failed_details（spec §6.1），
    所以这两个数只能由这个函数补上，漏写任何一条都会让前端看到错数字。
    """
    task = MagicMock()
    task.status = "fallback_running"
    task.completed_urls = 0
    task.failed_urls = 0
    task.total_urls = 3
    task.fallback_total = 3
    task.fallback_done = 0
    task.failed_details = []
    task.completed_at = None

    row = MagicMock()
    row.url = "https://c.com/3"
    row.fail_reason = None  # 故意留空，验证会回落到 FALLBACK_FAIL_REASON

    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]

    session = MagicMock()
    session.get = AsyncMock(return_value=task)
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    # `async with AsyncSessionLocal() as session` 里的 session 是 __aenter__ 的返回值，
    # 不是 AsyncSessionLocal() 本身——必须显式接上，否则拿到的是个子 mock。
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(service, "AsyncSessionLocal", MagicMock(return_value=cm)), \
         patch.object(service, "progress_bus") as bus:
        final = await service._settle_after_fallback("t1", ok=2)

    assert final == "partial_failed"
    assert task.status == "partial_failed"
    assert task.completed_urls == 2
    assert task.failed_urls == 1
    assert task.fallback_done == 3
    assert task.completed_at is not None
    assert task.failed_details == [{
        "url": "https://c.com/3", "code": 2001,
        "reason": service.FALLBACK_FAIL_REASON, "stage": "aibrowser",
    }]
    assert session.commit.await_count == 1
    # 终态那条事件必须带着修好的计数播出去，否则前端会定格在旧数字上
    assert bus.emit.call_count == 1
    assert bus.emit.call_args.args[0].status == "partial_failed"
