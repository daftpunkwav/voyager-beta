"""fetch_news「解析-钉住」SSRF 防护专项测试:全程离线(resolve 注入替身)。

覆盖:语法/字面量拒绝已在其余用例;本文件聚焦钉住机制本身——
Host 头保持原域名、连接目标是校验过的 IP、白名单外 302 到内网被拒且不触内网。
"""

import httpx
import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

import services.sources.modules.news.capabilities as news_caps
from services.sources.capabilities import registry
from services.sources.modules.news.store import NewsStore

USER_CTX = ActorContext(actor=LOCAL_USER)

_PUBLIC_IP = "93.184.216.34"  # 测试用假公网 IP(不出网)


def _fake_resolver(mapping: dict[str, list[str]]):
    async def resolve(host: str, port: int) -> list[str]:
        if host not in mapping:
            raise OSError(f"测试解析器未知主机: {host}")
        return mapping[host]

    return resolve


@pytest.fixture()
def news_env(tmp_path, monkeypatch):
    """独立 NewsStore + 注入式 resolver + MockTransport 客户端。"""
    calls: list[httpx.Request] = []

    def install(handler):
        news_caps.init_deps(news_caps.NewsDeps(
            store=NewsStore(tmp_path / "news.db"), bus=None,
            resolve=_fake_resolver({"github.com": [_PUBLIC_IP]}),
        ))
        orig = httpx.AsyncClient

        def recording_handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        def factory(**kw):
            kw.pop("follow_redirects", None)
            return orig(transport=httpx.MockTransport(recording_handler),
                        follow_redirects=False, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", factory)
        return calls

    return install


class TestPinnedFetch:
    async def test_request_targets_pinned_ip_with_original_host(self, news_env) -> None:
        """连接目标是被校验的 IP,而 Host 头仍是原域名(路由/SNI 语义保持)。"""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["host"] = request.headers.get("host")
            assert request.url.host == _PUBLIC_IP  # 连接目标是钉住的 IP
            return httpx.Response(200, text="<title>ok</title>正文")

        news_env(handler)
        await execute(registry, "fetch_news", USER_CTX,
                      {"url": "https://github.com/x"})
        assert seen["host"] == "github.com"

    async def test_redirect_to_internal_blocked_before_request(self, news_env) -> None:
        """外部页 302 → 内网字面量:第二跳在地址校验处被拒,绝不触达内网。"""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.host == _PUBLIC_IP:  # 第一跳(钉住后的 IP 形态)
                return httpx.Response(302, headers={
                    "location": "http://169.254.169.254/latest/meta-data"})
            raise AssertionError(f"内网地址被实际请求: {request.url}")

        news_env(handler)
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "fetch_news", USER_CTX,
                          {"url": "https://github.com/start"})
        assert exc.value.body.code == "SOURCES.FORBIDDEN"
        assert len(calls) == 1  # 只有第一跳出网
