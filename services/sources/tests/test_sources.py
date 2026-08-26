"""sources 服务测试:repo 导入/排序/元数据/密钥边界 + books/news 最小集 + 聚合注册表。

GitHub API 与 git clone 一律 mock,测试不触网、不触 git。
"""

import asyncio
from pathlib import Path

import httpx
import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_secrets import SecretStore

from services.sources.capabilities import SourcesDeps, init_all, registry
from services.sources.modules.books.store import BookStore
from services.sources.modules.news.store import NewsStore
from services.sources.modules.repo import github as github_mod
from services.sources.modules.repo.store import RepoStore
from services.sources.modules.repo.worker import RepoWorker

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def _mock_github(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/readme"):
            import base64
            return httpx.Response(200, json={
                "encoding": "base64",
                "content": base64.b64encode("# 你好 README".encode()).decode(),
            })
        if "/search/" in path:
            return httpx.Response(200, json={"items": [{
                "name": "langgraph", "html_url": "https://github.com/langchain-ai/langgraph",
                "owner": {"login": "langchain-ai"}, "description": "编排",
                "stargazers_count": 100, "language": "Python"}]})
        if path.endswith("/starred"):
            return httpx.Response(200, json=[{
                "name": "langgraph", "html_url": "https://github.com/langchain-ai/langgraph",
                "owner": {"login": "langchain-ai"}, "description": "星标仓库",
                "stargazers_count": 100, "language": "Python"}])
        return httpx.Response(200, json={
            "name": path.rsplit("/", 1)[-1], "html_url": f"https://github.com{path}",
            "description": "测试仓库", "stargazers_count": 42, "language": "Python"})

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        github_mod.httpx, "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(handler), **kw),
    )


@pytest.fixture()
def deps(tmp_path, monkeypatch):
    _mock_github(monkeypatch)
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    queue: asyncio.Queue = asyncio.Queue()
    d = SourcesDeps(
        repo_store=RepoStore(tmp_path / "repo.db"),
        book_store=BookStore(tmp_path / "books.db"),
        news_store=NewsStore(tmp_path / "news.db"),
        secrets=SecretStore(tmp_path / "secrets.db", key_material="t"),
        bus=bus, repo_queue=queue, workspace=tmp_path / "ws",
    )
    init_all(d)
    yield d, log
    d.repo_store.close()
    d.book_store.close()
    d.news_store.close()
    log.close()


class TestRepo:
    async def test_import_registers_and_enqueues(self, deps) -> None:
        d, log = deps
        ref = await execute(registry, "import_repo", USER_CTX,
                            {"url": "https://github.com/langchain-ai/langgraph"})
        repo = d.repo_store.get(ref.job_id)
        assert repo["status"] == "importing"
        assert repo["readme"].startswith("# 你好")  # README 导入时缓存
        assert repo["stars"] == 42
        assert d.repo_queue.qsize() == 1  # 已入队等克隆
        events = [e.type for _, e in log.read_after()]
        assert "source.added" in events

    async def test_duplicate_conflict(self, deps) -> None:
        d, _ = deps
        d.repo_store.add({"name": "a", "url": "https://github.com/o/a", "status": "ready"})
        with pytest.raises(ServiceError, match="已导入"):
            await execute(registry, "import_repo", USER_CTX,
                          {"url": "https://github.com/o/a"})

    async def test_sort_by_name_and_summary_hides_readme(self, deps) -> None:
        d, _ = deps
        for name in ("beta", "alpha", "gamma"):
            d.repo_store.add({"name": name, "url": f"https://github.com/o/{name}",
                              "status": "ready", "readme": "长文"})
        out = await execute(registry, "sort_repos", AGENT_CTX, {"by": "name"})
        assert [r["name"] for r in out] == ["alpha", "beta", "gamma"]  # agent 同权排序
        assert "readme" not in out[0]  # 列表摘要不含正文(§9.20)
        full = await execute(registry, "get_readme", AGENT_CTX, {"repo_id": out[0]["id"]})
        assert full["readme"] == "长文"

    async def test_meta_and_categories(self, deps) -> None:
        d, _ = deps
        rid = d.repo_store.add({"name": "a", "url": "https://github.com/o/a"})
        await execute(registry, "set_repo_meta", USER_CTX,
                      {"repo_id": rid, "category": "Agent 框架", "tags": ["py", "图谱"],
                       "progress": "learning"})
        assert await execute(registry, "list_categories", USER_CTX, {}) == ["Agent 框架"]
        repo = d.repo_store.get(rid)
        assert repo["tags"] == ["py", "图谱"] and repo["progress"] == "learning"

    async def test_remove_repo(self, deps) -> None:
        d, _ = deps
        rid = d.repo_store.add({"name": "a", "url": "https://github.com/o/a"})
        await execute(registry, "remove_repo", USER_CTX, {"repo_id": rid})
        assert d.repo_store.get(rid) is None

    async def test_search_remote(self, deps) -> None:
        out = await execute(registry, "search_remote_repos", AGENT_CTX,
                            {"query": "langgraph"})
        assert out[0]["name"] == "langgraph"

    async def test_list_starred(self, deps) -> None:
        """真实端点为 /users/{u}/starred(迁移期曾误写 /stars)。"""
        out = await execute(registry, "list_starred_repos", USER_CTX,
                            {"username": "someone"})
        assert out[0]["owner"] == "langchain-ai" and out[0]["stars"] == 100

    async def test_github_token_user_only(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_github_token", AGENT_CTX, {"token": "t"})
        assert exc.value.body.code == "SOURCES.FORBIDDEN"


class TestRepoWorker:
    async def test_clone_then_ready(self, deps, tmp_path) -> None:
        d, log = deps
        rid = d.repo_store.add({"owner": "o", "name": "r",
                                "url": "https://github.com/o/r"})

        async def fake_clone(owner: str, name: str, dest: Path) -> None:
            dest.mkdir(parents=True)
            (dest / "README.md").write_text("ok", encoding="utf-8")

        worker = RepoWorker(d.repo_store, EventBus(log), d.repo_queue,
                            tmp_path / "ws", clone_fn=fake_clone)
        await worker.start()
        d.repo_queue.put_nowait(rid)
        await asyncio.sleep(0.05)
        await worker.stop()
        repo = d.repo_store.get(rid)
        assert repo["status"] == "ready" and "o__r" in repo["local_path"]
        types = [e.type for _, e in log.read_after(types=["source.ready", "task.failed"])]
        assert types == ["source.ready"]  # agent 的 observe 靠它接手(§9.2)

    async def test_clone_failure_marks_failed(self, deps, tmp_path) -> None:
        d, _log = deps
        rid = d.repo_store.add({"owner": "o", "name": "bad",
                                "url": "https://github.com/o/bad"})

        async def boom(owner, name, dest) -> None:
            raise RuntimeError("网络不可达")

        worker = RepoWorker(d.repo_store, None, d.repo_queue,
                            tmp_path / "ws", clone_fn=boom)
        await worker.start()
        d.repo_queue.put_nowait(rid)
        await asyncio.sleep(0.05)
        await worker.stop()
        assert d.repo_store.get(rid)["status"] == "failed"


class TestBooksNews:
    async def test_book_lifecycle(self, deps, tmp_path) -> None:
        src = tmp_path / "book.md"
        src.write_text("# 章节一\n" + "内容" * 100, encoding="utf-8")
        book = await execute(registry, "add_book", USER_CTX,
                             {"title": "测试书", "file_path": str(src)})
        assert Path(book["local_path"]).is_file()  # 副本入 workspace/books
        chapter = await execute(registry, "get_chapter", USER_CTX,
                                {"book_id": book["id"], "length": 10})
        assert chapter["text"].startswith("# 章节一")
        await execute(registry, "remove_book", USER_CTX, {"book_id": book["id"]})
        assert await execute(registry, "list_books", USER_CTX, {}) == []

    async def test_add_book_sanitizes_title_filename(self, deps, tmp_path) -> None:
        """title 中的路径分隔符/保留字符不得让副本写逃逸 workspace/books。"""
        d, _ = deps
        src = tmp_path / "book.txt"
        src.write_text("hello", encoding="utf-8")
        book = await execute(registry, "add_book", USER_CTX,
                             {"title": '../../evil "name"', "file_path": str(src)})
        local = Path(book["local_path"])
        assert local.parent == Path(d.workspace) / "books"  # 未逃逸
        assert local.is_file()
        with pytest.raises(ServiceError, match="清洗后为空"):
            await execute(registry, "add_book", USER_CTX,
                          {"title": "..", "file_path": str(src)})

    async def test_news_add_and_get(self, deps) -> None:
        item = await execute(registry, "add_news", USER_CTX,
                             {"title": "AI 周报", "content": "正文" * 200})
        assert item["summary"]  # 列表摘要有截断摘要
        full = await execute(registry, "get_news", AGENT_CTX, {"news_id": item["id"]})
        assert len(full["content"]) > len(item["summary"])

    async def test_fetch_news_ssrf_guard(self, deps) -> None:
        """回环/链路本地/非 http 协议一律拒绝,不发起请求。"""
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "fetch_news", AGENT_CTX,
                          {"url": "http://127.0.0.1:8123/api/project-health"})
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "fetch_news", AGENT_CTX,
                          {"url": "http://169.254.169.254/latest/meta-data"})
        with pytest.raises(ServiceError, match="http/https"):
            await execute(registry, "fetch_news", AGENT_CTX,
                          {"url": "file:///etc/passwd"})


class TestAggregate:
    def test_registry_merges_all_modules(self) -> None:
        names = registry.names()
        assert {"import_repo", "add_book", "fetch_news"} <= set(names)
        assert len(names) == len(set(names))  # 无重名冲突
