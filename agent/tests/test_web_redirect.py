"""web_fetch 重定向逐跳校验测试(§9.9):白名单域 302 → 内网必须被拒。

SSRF 逻辑回归保护:重定向每一跳都重新过 policy,而非整链自动跟随。
全程 MockTransport,测试不触网。
"""

import httpx

import agent.tools.web as web_mod
from agent.policy import NetworkPolicy, PolicyEngine


def _client_factory(handler):
    orig = httpx.AsyncClient

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    return factory


def _fetch(monkeypatch, handler) -> object:
    monkeypatch.setattr(web_mod.httpx, "AsyncClient", _client_factory(handler))
    policy = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
    return web_mod.web_tools(policy)["web_fetch"].handler


async def test_redirect_to_internal_is_refused(monkeypatch) -> None:
    """白名单域名 302 → 链路本地地址:每一跳重新校验,内网跳不发请求。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "github.com":
            return httpx.Response(302, headers={
                "location": "http://169.254.169.254/latest/meta-data"})
        raise AssertionError(f"内网地址被实际请求: {request.url}")

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("http://github.com/redirect")

    assert len(calls) == 1  # 只打了第一跳
    # phase-33 后内网跳由「非全局字面量」规则拒绝(reason=拒绝环回或内网地址),
    # 在此之前走白名单拒绝;不锁定具体是哪条规则,任一生效即算拦截成功
    assert "[已拒绝]" in out and ("不在白名单" in out or "环回" in out or "内网" in out)


async def test_redirect_within_whitelist_follows(monkeypatch) -> None:
    """白名单内的重定向正常跟随到最终内容。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="done")

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("https://github.com/start")
    assert "HTTP 200" in out and "done" in out
