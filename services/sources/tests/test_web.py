"""web 子模块测试:save_url 全链(mock httpx)/SSRF 防护沿用(解析-钉住)/
手动录入/元数据/删除事件。全程离线(resolve 注入替身)。"""

import httpx
import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError

import services.sources.modules.web.capabilities as web_caps
from services.sources.capabilities import SourcesDeps, init_all, registry
from services.sources.modules.web.store import WebStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))

_PUBLIC_IP = "93.184.216.34"  # 测试用假公网 IP(不出网)


@pytest.fixture()
def deps(tmp_path):
    import asyncio

    from platform_eventbus import EventBus, EventLog
    from platform_secrets import SecretStore

    from services.sources.modules.doc.store import DocStore
    from services.sources.modules.repo.store import RepoStore

    log = EventLog(tmp_path / "events.db")
    d = SourcesDeps(
        repo_store=RepoStore(tmp_path / "repo.db"),
        doc_store=DocStore(tmp_path / "doc.db"),
        web_store=WebStore(tmp_path / "web.db"),
        secrets=SecretStore(tmp_path / "secrets.db", key_material="t"),
        bus=EventBus(log),
        repo_queue=asyncio.Queue(), doc_queue=asyncio.Queue(),
        workspace=tmp_path / "ws",
    )
    init_all(d)
    yield d, log
    d.repo_store.close()
    d.doc_store.close()
    d.web_store.close()
    log.close()


@pytest.fixture()
def web_env(deps, tmp_path, monkeypatch):
    """注入式 resolver + MockTransport 客户端;返回 (deps, log, calls)。"""
    d, log = deps
    calls: list[httpx.Request] = []

    async def resolve(host: str, port: int) -> list[str]:
        if host == "example.com":
            return [_PUBLIC_IP]
        raise OSError(f"测试解析器未知主机: {host}")

    web_caps.init_deps(web_caps.WebDeps(store=d.web_store, bus=d.bus, resolve=resolve))
    orig = httpx.AsyncClient

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="<title>测试页</title><p>正文第一段</p>")

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(recording_handler),
                    follow_redirects=False, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return d, log, calls


class TestSaveUrl:
    async def test_saves_page_with_extracted_content(self, web_env) -> None:
        _, log, _ = web_env
        page = await execute(registry, "save_url", USER_CTX,
                             {"url": "https://example.com/post/1",
                              "tags": ["教程"]})
        assert page["title"] == "测试页"
        assert "正文第一段" in page["content"]
        assert page["domain"] == "example.com"
        assert page["tags"] == ["教程"]
        types = [e.type for _, e in log.read_after()]
        assert "source.added" in types and "source.ready" in types

    async def test_pinned_ip_with_original_host(self, web_env) -> None:
        """连接目标是被校验的 IP,而 Host 头仍是原域名(路由/SNI 语义保持)。"""
        _, _, calls = web_env
        await execute(registry, "save_url", USER_CTX, {"url": "https://example.com/x"})
        assert calls and calls[0].url.host == _PUBLIC_IP
        assert calls[0].headers.get("host") == "example.com"

    async def test_ssrf_guards(self, deps) -> None:
        """回环/链路本地/非 http 协议一律拒绝,不发起请求。"""
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "save_url", USER_CTX,
                          {"url": "http://127.0.0.1:8123/api"})
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "save_url", USER_CTX,
                          {"url": "http://169.254.169.254/latest/meta-data"})
        with pytest.raises(ServiceError, match="http/https"):
            await execute(registry, "save_url", USER_CTX, {"url": "file:///etc/passwd"})

    async def test_resolved_loopback_rejected(self, deps) -> None:
        """域名解析到环回/IPv4-mapped 环回必须拒绝,不能只校验字面量。"""
        d, _ = deps

        async def resolve_loopback(host: str, port: int) -> list[str]:
            if host == "localtest.me":
                return ["127.0.0.1"]
            if host == "mapped.example":
                return ["::ffff:127.0.0.1"]
            raise OSError(host)

        web_caps.init_deps(web_caps.WebDeps(
            store=d.web_store, bus=d.bus, resolve=resolve_loopback))
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "save_url", USER_CTX,
                          {"url": "http://localtest.me/"})
        with pytest.raises(ServiceError, match="不在公网范围"):
            await execute(registry, "save_url", USER_CTX,
                          {"url": "http://mapped.example/"})


class TestPages:
    async def test_add_list_get_remove_event(self, web_env) -> None:
        _, log, _ = web_env
        page = await execute(registry, "add_page", USER_CTX,
                             {"title": "手动剪藏", "content": "正文" * 300,
                              "url": "https://example.com/a"})
        assert page["summary"]
        pages = await execute(registry, "list_pages", USER_CTX, {"query": "手动"})
        assert len(pages) == 1
        full = await execute(registry, "get_page", AGENT_CTX, {"page_id": page["id"]})
        assert len(full["content"]) > len(full["summary"])
        await execute(registry, "remove_page", USER_CTX, {"page_id": page["id"]})
        assert await execute(registry, "list_pages", USER_CTX, {}) == []
        types = [e.type for _, e in log.read_after(types=["source.removed"])]
        assert types == ["source.removed"]

    async def test_set_meta_and_validation(self, web_env) -> None:
        page = await execute(registry, "add_page", USER_CTX,
                             {"title": "旧标题", "content": "x"})
        updated = await execute(registry, "set_page_meta", USER_CTX,
                                {"page_id": page["id"], "title": "新标题",
                                 "tags": ["ai"]})
        assert updated["title"] == "新标题" and updated["tags"] == ["ai"]
        with pytest.raises(ServiceError, match="标签不合法"):
            await execute(registry, "set_page_meta", USER_CTX,
                          {"page_id": page["id"], "tags": ['q"q']})
        with pytest.raises(ServiceError, match="不存在"):
            await execute(registry, "get_page", USER_CTX, {"page_id": "ghost"})
