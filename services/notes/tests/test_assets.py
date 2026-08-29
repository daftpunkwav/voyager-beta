"""附件能力测试:add_asset 白名单/大小/workspace 边界 + 只读路由 + purge 连带清理。"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from services.notes.capabilities import registry
from services.notes.wiring import wire

USER_CTX = ActorContext(actor=LOCAL_USER)

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture()
def env(tmp_path):
    """完整 wire 装配(workspace 指向 tmp)+ 独立 FastAPI 挂附件路由。"""
    from platform_eventbus import EventBus, EventLog

    bus = EventBus(EventLog(tmp_path / "events.db"))
    w = wire(tmp_path / "data", bus=bus, workspace=tmp_path / "ws")
    (tmp_path / "ws").mkdir(exist_ok=True)
    app = FastAPI()
    from fastapi.responses import JSONResponse
    from platform_contracts import ServiceError as SE

    from services.notes.assets import build_assets_router

    app.include_router(build_assets_router(), prefix="/api/notes")

    @app.exception_handler(SE)
    async def _se(_req, exc: SE) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())
    yield w, tmp_path / "ws", TestClient(app)
    if w.close:
        w.close()
    bus.log.close() if hasattr(bus, "log") else None


class TestAddAsset:
    async def test_add_returns_markdown_reference(self, env) -> None:
        _, ws, _ = env
        src = ws / "pic.png"
        src.write_bytes(_PNG)
        out = await execute(registry, "add_asset", USER_CTX,
                            {"file_path": str(src), "filename": "截图.png"})
        assert out["asset_id"]
        assert out["url"] == f"/api/notes/assets/{out['asset_id']}"
        assert out["markdown"] == f"![截图.png](attachment://{out['asset_id']})"
        # 副本落 notes-assets,id 命名(内容寻址,不覆盖)
        assert Path(out["url"].rsplit("/", 1)[-1]).suffix == ".png" or (
            ws / "notes-assets" / f"{out['asset_id']}.png").is_file()

    async def test_rejects_non_image_and_missing(self, env, tmp_path) -> None:
        _, ws, _ = env
        bad = ws / "evil.exe"
        bad.write_bytes(b"MZ")
        with pytest.raises(ServiceError, match="不支持的图片格式"):
            await execute(registry, "add_asset", USER_CTX, {"file_path": str(bad)})
        with pytest.raises(ServiceError, match="文件不存在"):
            await execute(registry, "add_asset", USER_CTX,
                          {"file_path": str(ws / "nope.png")})

    async def test_rejects_outside_workspace(self, env, tmp_path) -> None:
        _, _ws, _ = env
        outside = tmp_path / "outside.png"
        outside.write_bytes(_PNG)
        with pytest.raises(ServiceError, match="workspace"):
            await execute(registry, "add_asset", USER_CTX,
                          {"file_path": str(outside)})

    async def test_rejects_symlink_outside_workspace(self, env, tmp_path) -> None:
        """通过 symlink 指向 workspace 外部文件仍应被拒绝。"""
        _, ws, _ = env
        real = tmp_path / "secret.png"
        real.write_bytes(_PNG)
        link = ws / "link.png"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("当前环境不支持创建 symlink")
        with pytest.raises(ServiceError, match="workspace"):
            await execute(registry, "add_asset", USER_CTX,
                          {"file_path": str(link)})


class TestAssetRoute:
    async def test_get_asset_file(self, env) -> None:
        _, ws, client = env
        src = ws / "p.png"
        src.write_bytes(_PNG)
        out = await execute(registry, "add_asset", USER_CTX,
                            {"file_path": str(src)})
        resp = client.get(f"/api/notes/assets/{out['asset_id']}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")
        assert resp.headers.get("cache-control") == "public, max-age=31536000, immutable"
        missing = client.get("/api/notes/assets/ghost")
        assert missing.status_code == 404


class TestPurgeCleansAssets:
    async def test_purge_note_removes_asset_files(self, env) -> None:
        _, ws, _ = env
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "带图笔记", "content": "有图"})
        nid = note["id"]
        src = ws / "p2.png"
        src.write_bytes(_PNG)
        asset = await execute(registry, "add_asset", USER_CTX,
                              {"file_path": str(src), "note_id": nid})
        asset_file = ws / "notes-assets" / f"{asset['asset_id']}.png"
        assert asset_file.is_file()
        await execute(registry, "purge_note", USER_CTX, {"note_id": nid})
        assert not asset_file.exists()  # purge 连带删附件文件


class TestRegistryCard:
    def test_service_json_includes_add_asset(self) -> None:
        import json
        card = json.loads(
            (Path(__file__).resolve().parents[1] / "service.json").read_text("utf-8"))
        assert "add_asset" in card["capabilities"]
        assert set(card["capabilities"]) == set(registry.names())
