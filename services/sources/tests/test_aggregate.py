"""跨类型统一资源流测试:list_sources / search_sources / sources_stats + 旧库迁移。"""

import asyncio

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_secrets import SecretStore

from services.sources.capabilities import SourcesDeps, init_all, registry
from services.sources.migration import migrate_legacy_books_news
from services.sources.modules.doc.store import DocStore
from services.sources.modules.repo.store import RepoStore
from services.sources.modules.web.store import WebStore

USER_CTX = ActorContext(actor=LOCAL_USER)


@pytest.fixture()
def deps(tmp_path):
    d = SourcesDeps(
        repo_store=RepoStore(tmp_path / "repo.db"),
        doc_store=DocStore(tmp_path / "doc.db"),
        web_store=WebStore(tmp_path / "web.db"),
        secrets=SecretStore(tmp_path / "secrets.db", key_material="t"),
        bus=None,
        repo_queue=asyncio.Queue(), doc_queue=asyncio.Queue(),
        workspace=tmp_path / "ws",
    )
    init_all(d)
    yield d
    d.repo_store.close()
    d.doc_store.close()
    d.web_store.close()


def _seed(d: SourcesDeps) -> dict[str, str]:
    d.repo_store.add({"name": "langgraph", "url": "https://github.com/o/langgraph",
                      "description": "编排框架", "status": "ready"})
    d.repo_store.add({"name": "requests", "url": "https://github.com/o/requests",
                      "description": "HTTP", "status": "failed"})
    doc_id = d.doc_store.add({"title": "深度学习手册", "filename": "dl.pdf",
                              "ext": ".pdf", "status": "ready"})
    d.doc_store.replace_sections(doc_id, [
        {"section_no": 1, "title": "引言", "page_start": 1, "page_end": 3,
         "text": "神经网络基础。" + "背景" * 50}])
    d.web_store.add({"title": "注意力机制详解", "url": "https://a.com/1",
                     "domain": "a.com", "summary": "注意力", "content": "注意力机制文章"})
    return {"doc_id": doc_id}


class TestListSources:
    async def test_merged_all_kinds_sorted_by_added(self, deps) -> None:
        _seed(deps)
        out = await execute(registry, "list_sources", USER_CTX, {})
        kinds = [r["kind"] for r in out]
        assert set(kinds) == {"repo", "doc", "web"}
        added = [r["added_ts"] for r in out]
        assert added == sorted(added, reverse=True)  # 默认按加入时间倒序

    async def test_kind_filter_and_unknown_rejected(self, deps) -> None:
        _seed(deps)
        docs = await execute(registry, "list_sources", USER_CTX, {"kind": "doc"})
        assert all(r["kind"] == "doc" for r in docs)
        with pytest.raises(ServiceError, match="未知资源类型"):
            await execute(registry, "list_sources", USER_CTX, {"kind": "video"})

    async def test_status_and_query_filters(self, deps) -> None:
        _seed(deps)
        failed = await execute(registry, "list_sources", USER_CTX,
                               {"status": "failed"})
        assert [r["title"] for r in failed] == ["requests"]
        hits = await execute(registry, "list_sources", USER_CTX, {"query": "手册"})
        assert [r["title"] for r in hits] == ["深度学习手册"]

    async def test_title_sort(self, deps) -> None:
        _seed(deps)
        out = await execute(registry, "list_sources", USER_CTX,
                            {"sort": "title", "desc": False})
        titles = [r["title"] for r in out]
        assert titles == sorted(titles)

    async def test_limit_2000_not_capped_at_500(self, deps) -> None:
        """帽抬到 2000(phase-14):graph L0 按 kind 取 2000 不被旧 500 帽静默截断。"""
        for i in range(501):  # 501 = 能区分「全量」与「被 500 截断」的最小行数
            deps.web_store.add({"title": f"页 {i}", "url": f"https://a.com/{i}",
                                "domain": "a.com"})
        out = await execute(registry, "list_sources", USER_CTX,
                            {"kind": "web", "limit": 2000})
        assert len(out) == 501


class TestSearchSources:
    async def test_title_hit_and_section_hit(self, deps) -> None:
        d = _seed(deps)
        out = await execute(registry, "search_sources", USER_CTX,
                            {"query": "注意力"})
        # 标题命中(web)+ 分章正文未含注意力;再查正文词
        assert any(r["kind"] == "web" and r["title"] == "注意力机制详解" for r in out)
        out2 = await execute(registry, "search_sources", USER_CTX,
                             {"query": "神经网络"})
        hit = next(r for r in out2 if r.get("match"))
        assert hit["id"] == d["doc_id"] and hit["match"]["section_no"] == 1
        assert "神经网络" in hit["match"]["snippet"]

    async def test_empty_query_rejected(self, deps) -> None:
        with pytest.raises(ServiceError, match="query 不能为空"):
            await execute(registry, "search_sources", USER_CTX, {"query": " "})


class TestSourcesStats:
    async def test_counts_per_kind_and_lifecycle(self, deps) -> None:
        _seed(deps)
        stats = await execute(registry, "sources_stats", USER_CTX, {})
        assert stats["repo"] == 2 and stats["doc"] == 1 and stats["web"] == 1
        assert stats["failed"] == 1 and stats["importing"] == 0


class TestMigration:
    def test_books_and_news_migrated(self, tmp_path) -> None:
        import sqlite3
        legacy_books = tmp_path / "books.db"
        conn = sqlite3.connect(str(legacy_books))
        conn.executescript(
            "CREATE TABLE books (id TEXT PRIMARY KEY, title TEXT NOT NULL,"
            " author TEXT NOT NULL DEFAULT '', format TEXT NOT NULL DEFAULT '',"
            " local_path TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',"
            " added_ts REAL NOT NULL);")
        conn.execute("INSERT INTO books VALUES ('b1', '旧书', '', '.txt',"
                     " '/ws/旧书.txt', '', 100.0)")
        conn.commit()
        conn.close()
        legacy_news = tmp_path / "news.db"
        conn = sqlite3.connect(str(legacy_news))
        conn.executescript(
            "CREATE TABLE news (id TEXT PRIMARY KEY, title TEXT NOT NULL,"
            " url TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',"
            " content TEXT NOT NULL DEFAULT '', added_ts REAL NOT NULL);")
        conn.execute("INSERT INTO news VALUES ('n1', '旧新闻',"
                     " 'https://x.com/a', '摘要', '正文', 200.0)")
        conn.commit()
        conn.close()

        migrate_legacy_books_news(tmp_path)
        doc_conn = sqlite3.connect(str(tmp_path / "doc.db"))
        rows = doc_conn.execute(
            "SELECT id, title, status FROM documents").fetchall()
        doc_conn.close()
        assert rows == [("b1", "旧书", "stored")]
        web_conn = sqlite3.connect(str(tmp_path / "web.db"))
        rows = web_conn.execute(
            "SELECT id, title, domain FROM webpages").fetchall()
        web_conn.close()
        assert rows == [("n1", "旧新闻", "x.com")]
        assert not legacy_books.exists() and not legacy_news.exists()  # 改名 .bak
        assert (tmp_path / "books.db.bak").exists()

    def test_idempotent_when_no_legacy(self, tmp_path) -> None:
        migrate_legacy_books_news(tmp_path)  # 无旧库:静默跳过,不建新库
        assert not (tmp_path / "doc.db").exists()
