"""索引全链路集成:HTTP enqueue -> scheduler 跑完(Python 引擎,测试内强制)
-> 事件链(task.progress/completed + graph.engine.fallback)-> query_graph
有节点与边;手建节点与索引节点同图;agent 桥可达图谱能力。
"""

import time

from fastapi.testclient import TestClient

from deploy.backend import build


def _make_toy_repo(root) -> str:
    """tmp 目录造一个小 python 文件树(main 调 helper,helper 调 utils)。"""
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "toy"
    repo.mkdir()
    (repo / "main.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper.go()\n", encoding="utf-8")
    (repo / "helper.py").write_text(
        "import utils\n\n"
        "def go():\n"
        "    return utils.answer()\n", encoding="utf-8")
    (repo / "utils.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    return str(repo)


def _wait_job_done(client, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = client.post("/api/graph/capabilities/list_index_jobs",
                           json={}).json()["result"]
        job = next((j for j in jobs if j["id"] == job_id), None)
        if job and job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"索引任务超时: {job_id}")


class TestIndexPipeline:
    def test_full_chain_python_engine(self, tmp_path) -> None:
        """enqueue 202 -> scheduler -> fallback 事件 -> 图有节点与调用边。"""
        ws = tmp_path / "ws"
        repo_path = _make_toy_repo(ws)
        app = build(tmp_path / "data", ws)
        backend = app.state.backend
        with TestClient(app) as client:
            resp = client.post("/api/graph/capabilities/enqueue_index", json={
                "project": "toy", "repo_path": repo_path,
            })
            assert resp.status_code == 202  # JobRef(坑:长任务只入队)
            job_id = resp.json()["job"]["job_id"]

            job = _wait_job_done(client, job_id)
            assert job["status"] == "done", job["error"]
            assert job["error"] == ""

            # 事件链:进度 + 完成 + 引擎回退(默认无 C sidecar,诚实呈现)
            types = [e.type for _, e in backend.log.read_after()]
            assert "task.progress" in types
            assert "task.completed" in types
            assert "graph.engine.fallback" in types

            info = client.post("/api/graph/capabilities/engine_info",
                               json={}).json()["result"]
            assert info["engine"] == "python"  # 或 fallback 事件:两者都算诚实

            graph = client.post("/api/graph/capabilities/query_graph",
                                json={"project": "toy"}).json()["result"]
            names = {n["name"] for n in graph["nodes"]}
            assert {"run", "go", "answer"} <= names  # 函数节点进图
            assert len(graph["edges"]) > 0  # 边也进图(带 id 映射)
            ids = {n["id"] for n in graph["nodes"]}
            assert all(e["src"] in ids and e["dst"] in ids for e in graph["edges"])

            # 手建节点与引擎节点同图,来源可区分(§8.4)
            created = client.post("/api/graph/capabilities/set_node", json={
                "project": "toy", "label": "Concept", "name": "ReAct 模式",
            }).json()["result"]
            assert created["source"] == "manual"
            code_nodes = [n for n in graph["nodes"] if n["source"] == "code"]
            assert code_nodes

            # 两级加载的近端:get_subgraph 能展开
            fn = next(n for n in graph["nodes"] if n["name"] == "run")
            sub = client.post("/api/graph/capabilities/get_subgraph", json={
                "project": "toy", "node_id": fn["id"], "depth": 1,
            }).json()["result"]
            assert len(sub["nodes"]) >= 1

    def test_queue_cancel_and_manual_project(self, tmp_path) -> None:
        """排队中可取消;手建项目名建图(不依赖资源库)。"""
        ws = tmp_path / "ws2"
        repo_path = _make_toy_repo(ws / "another")
        app = build(tmp_path / "data2", ws)
        with TestClient(app) as client:
            # 先占住调度器(concurrency=1):长任务在跑,第二个排队可取消
            busy = client.post("/api/graph/capabilities/enqueue_index", json={
                "project": "busy", "repo_path": repo_path,
            }).json()["job"]["job_id"]
            assert busy
            jid = client.post("/api/graph/capabilities/enqueue_index", json={
                "project": "later", "repo_path": repo_path, "priority": 200,
            }).json()["job"]["job_id"]
            out = client.post("/api/graph/capabilities/cancel_index",
                              json={"job_id": jid}).json()["result"]
            assert out == {"cancelled": jid}
            jobs = client.post("/api/graph/capabilities/list_index_jobs",
                               json={}).json()["result"]
            later = next(j for j in jobs if j["id"] == jid)
            assert later["status"] == "cancelled"

    def test_agent_bridge_reaches_graph_tools(self, tmp_path) -> None:
        """领域能力经桥进入 agent 工具集(图谱讲解/建图的先决条件)。"""
        app = build(tmp_path / "data3", tmp_path / "ws3")
        backend = app.state.backend
        names = backend.agent.spawner._toolbelt.names()
        for expect in ("graph__enqueue_index", "graph__query_graph",
                       "graph__set_node", "graph__set_relationship",
                       "graph__get_subgraph"):
            assert expect in names
        # Atlas 能力面裁剪后仍保留图谱工具(未索引先入队的纪律);
        # phase-06 起白名单是 graph__* 前缀授予,对真名册展开后必须含这些工具
        from agent.personas import PERSONAS
        allow = PERSONAS["graph_guide"].tool_allow or ()
        assert "graph__*" in allow
        trimmed_names = set(
            backend.agent.spawner._toolbelt.trimmed(allow).names()
        )
        assert {"graph__enqueue_index", "graph__graph_guide"} <= trimmed_names


class TestL0ViaProvider:
    def test_l0_provider_through_list_sources(self, tmp_path) -> None:
        """phase-14:装配根资源目录 provider 经 list_sources 能力取数
        (deploy 不读 STORES);两条同 tag 文档进 L0 并产出 RELATED 边。"""
        app = build(tmp_path / "data", tmp_path / "ws",
                    parse_fn=lambda path, ext: [])
        with TestClient(app) as client:
            src = tmp_path / "ws" / "imports"
            src.mkdir(parents=True, exist_ok=True)
            for i, title in enumerate(("手册 A", "手册 B")):
                f = src / f"a{i}.md"
                f.write_text("内容", encoding="utf-8")
                ref = client.post("/api/sources/capabilities/add_document", json={
                    "file_path": str(f), "title": title, "tags": ["共享标签"]})
                assert ref.status_code == 202
            # 等两份文档 ready(L0 排除 importing/parsing/failed)
            stats = {}
            deadline = time.time() + 8
            while time.time() < deadline:
                stats = client.post("/api/sources/capabilities/sources_stats",
                                    json={}).json()["result"]
                if stats.get("doc") == 2 and not stats.get("importing") \
                        and not stats.get("parsing"):
                    break
                time.sleep(0.1)
            else:
                raise AssertionError(f"文档未就绪: {stats}")

            ref = client.post("/api/graph/capabilities/enqueue_l0",
                              json={"kinds": ["doc"]})
            assert ref.status_code == 202
            job = _wait_job_done(client, ref.json()["job"]["job_id"])
            assert job["status"] == "done", job["error"]

            view = client.post("/api/graph/capabilities/l0_view",
                               json={"kinds": ["doc"]}).json()["result"]
            assert len(view["nodes"]) == 2  # provider 不是空回调
            assert view["edges"] and view["edges"][0]["type"] == "RELATED"
