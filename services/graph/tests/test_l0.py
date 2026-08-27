"""L0 跨资源关联管线与能力测试(§8.4 分层):kinds 校验、标签重合建边、
重建保留 AI 产出、l0_view 过滤、独立形态无资源目录报错。"""

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from services.graph.capabilities import Deps, init_deps, registry
from services.graph.engines.adapter import EngineAdapter
from services.graph.index_queue import IndexQueue
from services.graph.pipelines.l0.relate import L0_PROJECT, run_l0
from services.graph.store import GraphStore

USER_CTX = ActorContext(actor=LOCAL_USER)


@pytest.fixture()
def deps(tmp_path):
    d = Deps(
        store=GraphStore(tmp_path / "graph.db"),
        queue=IndexQueue(tmp_path / "index.db"),
        adapter=EngineAdapter(c_base_url="",
                              python_data_root=tmp_path / "pyengine", bus=None),
        bus=None,
    )
    init_deps(d)
    yield d
    d.store.close()
    d.queue.close()


def _provider(resources: list[dict]):
    return lambda kinds: [r for r in resources if r["kind"] in kinds]


def _res(rid: str, kind: str, title: str, tags: list[str],
         status: str = "ready") -> dict:
    return {"id": rid, "kind": kind, "title": title, "tags": tags,
            "category": "", "status": status, "subtitle": ""}


class TestRunL0:
    def test_shared_tags_create_related_edge(self, deps) -> None:
        store = deps.store
        provider = _provider([
            _res("a", "doc", "书 A", ["python", "入门"]),
            _res("b", "web", "页 B", ["python"]),
            _res("c", "repo", "仓 C", ["rust"]),
        ])
        out = run_l0(store, provider, kinds=["doc", "web", "repo"])
        assert out["resources"] == 3
        assert out["related_edges"] == 1  # 仅 A~B 共享 python
        view = store.query(L0_PROJECT)
        edge = view["edges"][0]
        assert edge["type"] == "RELATED"
        assert edge["attrs"]["shared_tags"] == ["python"]
        assert edge["source"] == "meta"

    def test_kind_filter_and_status_excluded(self, deps) -> None:
        store = deps.store
        provider = _provider([
            _res("a", "doc", "书 A", ["t"]),
            _res("b", "web", "页 B", ["t"]),
            _res("c", "repo", "失败仓", ["t"], status="failed"),
            _res("d", "repo", "导入中仓", ["t"], status="importing"),
        ])
        out = run_l0(store, provider, kinds=["doc", "web", "repo"])
        # repo 的 failed/importing 不参与:A~B 仍建边
        assert out["resources"] == 2
        assert out["related_edges"] == 1

    def test_rebuild_keeps_ai_and_drops_stale(self, deps) -> None:
        store = deps.store
        provider = _provider([_res("a", "doc", "书 A", ["t"])])
        run_l0(store, provider, kinds=["doc"])
        # AI 在 universe 空间写概念节点与语义边
        concept = store.upsert_node(L0_PROJECT, "Concept", "依赖注入",
                                    "concept:di", source="ai", actor="agent")
        res_node = store.query(L0_PROJECT, keyword="doc:a")["nodes"][0]
        store.upsert_edge(L0_PROJECT, concept["id"], res_node["id"],
                          "MENTIONS", source="ai", actor="agent")
        # 重跑:资源 a 消失 → 其 Resource 节点清理,AI 节点保留
        out = run_l0(store, _provider([]), kinds=["doc"])
        assert out["nodes"] == 0
        names = [n["name"] for n in store.query(L0_PROJECT)["nodes"]]
        assert names == ["依赖注入"]

    def test_missing_provider_raises(self, deps) -> None:
        with pytest.raises(RuntimeError, match="聚合形态"):
            run_l0(deps.store, None, kinds=["doc"])

    def test_invalid_kind_raises(self, deps) -> None:
        with pytest.raises(ValueError, match="未知的资源种类"):
            run_l0(deps.store, _provider([]), kinds=["book"])


class TestL0Capabilities:
    async def test_enqueue_l0_validates_kinds(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "enqueue_l0", USER_CTX, {"kinds": ["book"]})
        assert exc.value.body.code == "GRAPH.INVALID_INPUT"
        with pytest.raises(ServiceError):
            await execute(registry, "enqueue_l0", USER_CTX, {"kinds": []})

    async def test_enqueue_l0_queues_job_with_level(self, deps) -> None:
        ref = await execute(registry, "enqueue_l0", USER_CTX,
                            {"kinds": ["web", "repo"]})
        job = deps.queue.get(ref.job_id)
        assert job["level"] == "l0"
        assert job["kinds"] == ["repo", "web"]  # 去重排序,确定性
        assert job["project"] == L0_PROJECT

    async def test_enqueue_index_keeps_l1_level(self, deps) -> None:
        ref = await execute(registry, "enqueue_index", USER_CTX,
                            {"project": "p", "repo_path": "/tmp/p"})
        job = deps.queue.get(ref.job_id)
        assert job["level"] == "l1" and job["kinds"] == []

    async def test_l0_view_filters_by_kind(self, deps) -> None:
        store = deps.store
        run_l0(store, _provider([
            _res("a", "doc", "书 A", ["t"]),
            _res("b", "web", "页 B", ["t"]),
        ]), kinds=["doc", "web"])
        view = await execute(registry, "l0_view", USER_CTX, {"kinds": ["doc"]})
        assert [n["attrs"]["kind"] for n in view["nodes"]] == ["doc"]
        assert view["edges"] == []  # 单节点无边
        full = await execute(registry, "l0_view", USER_CTX, {})
        assert len(full["nodes"]) == 2 and len(full["edges"]) == 1
