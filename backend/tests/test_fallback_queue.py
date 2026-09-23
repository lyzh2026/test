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


# ====== 三个只有靠突变测试才发现得了的守卫 ======


def _fake_task() -> MagicMock:
    task = MagicMock()
    task.id = "t1"
    task.status = "pending"
    task.failed_details = []
    task.failed_urls = 0
    task.completed_urls = 0
    task.total_urls = 1
    task.fallback_done = 0
    task.fallback_total = 0
    task.completed_at = None
    return task


def _fake_session(task: MagicMock) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=task)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _session_cm(session: MagicMock) -> MagicMock:
    """`async with AsyncSessionLocal() as session` 拿到的是 __aenter__ 的返回值。"""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _patch_crawl_job(*, aibrowser_enabled: bool, crawl_result):
    """run_crawl_job 的公共 patch 组：返回 (ExitStack, 资源字典)。"""
    from contextlib import ExitStack

    task = _fake_task()
    session = _fake_session(task)
    stack = ExitStack()
    ab = stack.enter_context(patch.object(service, "ai_browser"))
    rc = stack.enter_context(patch.object(service, "redis_client"))
    rl = stack.enter_context(patch.object(service, "domain_rate_limiter"))
    stack.enter_context(patch.object(service, "progress_bus"))
    rend = stack.enter_context(patch.object(service, "renderer"))
    crawl = stack.enter_context(patch.object(service, "_crawl_one", AsyncMock(return_value=crawl_result)))
    stack.enter_context(patch.object(service, "AsyncSessionLocal", _session_cm(session)))

    ab.is_ai_browser_enabled = AsyncMock(return_value=aibrowser_enabled)
    ab.load_route_policy = AsyncMock(return_value={})
    rc.smembers = AsyncMock(return_value=set())
    rc.sadd = AsyncMock()
    rc.expire = AsyncMock()
    rl.acquire = AsyncMock()
    rl.release = AsyncMock()
    rend.flush_render_stats = AsyncMock()

    return stack, {"task": task, "session": session, "crawl": crawl}


@pytest.mark.asyncio
async def test_settlement_survives_none_results():
    """pin (i)：`_one` 因任务取消返回 None（service.py:357-360）时，结算块不能拿 None 去 .get。

    没有 `res is not None` 这个守卫，`None.get("code", 2001)` 抛 AttributeError → 走
    fatal 分支，任务被写成「任务异常终止」而不是正常结算。
    """
    stack, env = _patch_crawl_job(aibrowser_enabled=False, crawl_result=None)
    with stack:
        await service.run_crawl_job("t1", ["https://a.com/1"])

    task = env["task"]
    assert task.status == "failed"
    assert task.failed_urls == 1  # 正常结算：failed 计数为 1
    assert task.completed_at is not None
    # 有守卫时 None 不进 failed_details；没有守卫时 fatal 分支会追加 stage='job' 明细
    assert task.failed_details == []


@pytest.mark.asyncio
async def test_fatal_error_during_drain_leaves_task_failed():
    """pin (ii)：drain 中途致命异常时，finally 谓词必须也认 fallback_running。

    谓词只写 ("running",) 的话，任务会永远卡在 fallback_running——前端一直转圈。
    """
    stack, env = _patch_crawl_job(
        aibrowser_enabled=True,
        crawl_result={"ok": False, "fallback": True, "reason": "RENDER_FAILED", "stage": "render"},
    )
    with stack, patch.object(
        service, "_drain_fallback_queue", AsyncMock(side_effect=RuntimeError("drain boom"))
    ):
        await service.run_crawl_job("t1", ["https://a.com/1"])

    task = env["task"]
    assert task.status == "failed"
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_task_accepts_fallback_running():
    """pin (iii)：兜底窗口内的任务必须可取消，否则用户点了没反应。"""
    task = _fake_task()
    task.status = "fallback_running"
    session = _fake_session(task)
    try:
        with patch.object(service, "AsyncSessionLocal", _session_cm(session)), \
             patch.object(service, "scheduler"), \
             patch.object(service, "progress_bus"):
            ok = await service.cancel_task("t-cancel-fb")
        assert ok is True
        assert task.status == "cancelled"
        assert task.completed_at is not None
    finally:
        service._cancelled_tasks.discard("t-cancel-fb")


@pytest.mark.asyncio
async def test_resume_scans_by_status_not_by_pending_rows():
    """F1 回归：启动扫描必须按 status='fallback_running' 选任务。

    只扫「还有 state='pending' 行」的任务只能救「入队后、认领前」那几毫秒；真正的崩溃
    窗口是整个 drain（browse_with_ai 几十秒），那时 pending 行早已被一次性置 done。
    """
    task = MagicMock()
    task.target_date = date(2026, 9, 23)

    result = MagicMock()
    result.scalars.return_value.all.return_value = ["t1"]

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=task)

    drain = AsyncMock(return_value=(1, 0))
    settle = AsyncMock(return_value="completed")

    with patch.object(service, "AsyncSessionLocal", _session_cm(session)), \
         patch.object(service, "_drain_fallback_queue", drain), \
         patch.object(service, "_settle_after_fallback", settle):
        n = await service.resume_fallback_queues()

    assert n == 1
    drain.assert_awaited_once_with("t1", target_date=date(2026, 9, 23))
    settle.assert_awaited_once_with("t1", ok=1)

    # 断言扫的是 CrawlerTask.status，而不是 FallbackQueue.state='pending'
    stmt = session.execute.call_args_list[0].args[0]
    sql = str(stmt)
    assert "crawler_tasks" in sql
    assert "fallback_queue" not in sql
