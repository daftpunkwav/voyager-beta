"""graph 服务测试(§8.4):规范存储 upsert、AI 管线校验、队列、调度重试、
引擎回退、Python 引擎端到端索引小仓库、仓库关联。"""

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog

from services.graph.capabilities import Deps, init_deps, registry
from services.graph.engines.adapter import EngineAdapter
from services.graph.index_queue import IndexQueue
from services.graph.pipelines.code.analyze import analyze_repo
from services.graph.pipelines.code.relate import relate_repos
from services.graph.scheduler import IndexScheduler
from services.graph.store import GraphStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    d = Deps(
        store=GraphStore(tmp_path / "graph.db"),
        queue=IndexQueue(tmp_path / "index.db"),
        adapter=EngineAdapter(c_base_url="",  # 无 C sidecar:必回退
                              python_data_root=tmp_path / "pyengine", bus=bus),
        bus=bus,
    )
    init_deps(d)
    yield d, log
    d.store.close()
    d.queue.close()
    log.close()


class TestCanonicalStore:
    async def test_set_node_upsert_idempotent(self, deps) -> None:
        args = {"project": "p1", "label": "Concept", "name": "代理"}
        n1 = await execute(registry, "set_node", AGENT_CTX, args)
        n2 = await execute(registry, "set_node", AGENT_CTX,
                           {**args, "attrs": {"quote": "出自第 3 章"}})
        assert n1["id"] == n2["id"]  # upsert:重复写=更新
        assert n2["attrs"]["quote"] == "出自第 3 章"
        assert n2["source"] == "ai" and n2["actor"] == "agent.main"

    async def test_manual_source_distinguished(self, deps) -> None:
        n = await execute(registry, "set_node", USER_CTX,
                          {"project": "p1", "label": "Term", "name": "手建"})
        assert n["source"] == "manual"  # 同一图存储,来源可区分(§8.4)

    async def test_set_node_validation(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_node", USER_CTX,
                          {"project": "", "label": "Concept", "name": "x"})
        assert exc.value.body.code == "GRAPH.INVALID_INPUT"

    async def test_relationship_autocreates_placeholders(self, deps) -> None:
        rel = await execute(registry, "set_relationship", AGENT_CTX, {
            "project": "p1", "src": "人工智能", "dst": "机器学习",
            "type": "CONTAINS"})
        graph = await execute(registry, "query_graph", AGENT_CTX, {"project": "p1"})
        names = {n["name"] for n in graph["nodes"]}
        assert {"人工智能", "机器学习"} <= names  # 占位节点自动补
        assert rel["type"] == "CONTAINS"

    async def test_subgraph_and_stats(self, deps) -> None:
        d, _ = deps
        await execute(registry, "set_relationship", USER_CTX, {
            "project": "p2", "src": "A", "dst": "B", "type": "RELATES_TO"})
        a = d.store.get_node("p2", "Term", "A")
        sub = await execute(registry, "get_subgraph", USER_CTX,
                            {"project": "p2", "node_id": a["id"], "depth": 1})
        assert len(sub["nodes"]) == 2 and len(sub["edges"]) == 1
        stats = await execute(registry, "graph_stats", USER_CTX, {"project": "p2"})
        assert stats["total_nodes"] == 2


class TestQueue:
    async def test_priority_order_and_reorder(self, deps) -> None:
        d, _ = deps
        j1 = await execute(registry, "enqueue_index", USER_CTX,
                           {"project": "a", "repo_path": "/x"})
        j2 = await execute(registry, "enqueue_index", USER_CTX,
                           {"project": "b", "repo_path": "/y"})
        await execute(registry, "reorder_queue", USER_CTX,
                      {"job_id": j2.job_id, "priority": 1})
        assert d.queue.next()["project"] == "b"  # 优先级小者先
        await execute(registry, "cancel_index", USER_CTX, {"job_id": j1.job_id})
        assert d.queue.get(j1.job_id)["status"] == "cancelled"

    async def test_cancel_running_conflict(self, deps) -> None:
        d, _ = deps
        jid = d.queue.enqueue("p", "/x")
        d.queue.next()  # 变 running
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "cancel_index", USER_CTX, {"job_id": jid})
        assert exc.value.body.code == "GRAPH.CONFLICT"


class TestScheduler:
    async def test_retry_then_done(self, deps) -> None:
        d, log = deps
        attempts: list[str] = []

        async def flaky(job) -> None:
            attempts.append(job["id"])
            if len(attempts) < 2:
                raise RuntimeError("引擎闪退")

        sched = IndexScheduler(d.queue, flaky, EventBus(log),
                               max_attempts=3, backoff_base_s=0.01, idle_poll_s=0.01)
        jid = d.queue.enqueue("p", "/x")
        await sched.start()
        for _ in range(100):
            if d.queue.get(jid)["status"] == "done":
                break
            await asyncio_sleep()
        await sched.stop()
        assert d.queue.get(jid)["status"] == "done"
        assert len(attempts) == 2  # 第一次失败重试,第二次成功

    async def test_give_up_after_max_attempts(self, deps) -> None:
        d, _ = deps

        async def always_fail(job) -> None:
            raise RuntimeError("bad")

        sched = IndexScheduler(d.queue, always_fail, None,
                               max_attempts=2, backoff_base_s=0.01, idle_poll_s=0.01)
        jid = d.queue.enqueue("p", "/x")
        await sched.start()
        for _ in range(100):
            if d.queue.get(jid)["status"] == "failed":
                break
            await asyncio_sleep()
        await sched.stop()
        job = d.queue.get(jid)
        assert job["status"] == "failed" and job["attempts"] == 2


async def asyncio_sleep() -> None:
    import asyncio
    await asyncio.sleep(0.02)


class TestEngineFallback:
    async def test_auto_falls_back_with_event(self, deps) -> None:
        _, log = deps
        out = await execute(registry, "engine_info", USER_CTX, {})
        assert out["engine"] == "python"
        types = [e.type for _, e in log.read_after()]
        assert "graph.engine.fallback" in types  # 降级有事件,前端徽章可显示

    async def test_forced_c_unavailable_503(self, tmp_path) -> None:
        adapter = EngineAdapter(c_base_url="http://127.0.0.1:1",  # 不可达
                                python_data_root=tmp_path / "e", mode="c")
        with pytest.raises(ServiceError) as exc:
            await adapter.resolve()
        assert exc.value.body.code == "GRAPH.UNAVAILABLE"


class TestCodePipeline:
    async def test_index_tiny_repo_end_to_end(self, deps, tmp_path) -> None:
        """Python 引擎端到端:索引一个玩具仓库,规范存储有节点。"""
        repo = tmp_path / "toy"
        repo.mkdir()
        (repo / "main.py").write_text(
            "import helper\n\ndef run():\n    return helper.go()\n", encoding="utf-8")
        (repo / "helper.py").write_text("def go():\n    return 1\n", encoding="utf-8")
        d, _ = deps
        result = await analyze_repo(d.adapter, d.store, project="toy",
                                    repo_path=str(repo))
        assert result["engine"] == "python"
        graph = d.store.query("toy")
        names = {n["name"] for n in graph["nodes"]}
        assert "run" in names and "go" in names  # 函数节点进来了
        code_nodes = [n for n in graph["nodes"] if n["source"] == "code"]
        assert code_nodes  # 来源标记为程序化管线

    async def test_relate_shared_dependency(self, deps) -> None:
        d, _ = deps
        for proj in ("web-a", "web-b"):
            nid = d.store.upsert_node(proj, "Module", "app", "app",
                                      {"import_target": "fastapi"},
                                      source="code", actor="engine.python")["id"]
            assert nid
        out = relate_repos(d.store, ["web-a", "web-b"])
        assert out["cross_edges"] >= 1
        cross = d.store.query("cross-repo")
        assert cross["edges"][0]["type"] == "CROSS_REPO"
