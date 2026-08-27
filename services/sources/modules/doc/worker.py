"""doc 解析 worker(§8.2):解析队列 → 分章落库 → source.ready。

复刻 RepoWorker 的队列模式:CPU 密集的提取进线程池(事件循环不阻塞);
parse_fn 可注入,测试不触真实解析器。删除任务与解析同队列保序。
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, Event
from platform_eventbus import EventBus

from .extract import ExtractError, Section, extract_sections
from .store import DocStore

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.doc.worker")

#: (path, ext) -> list[Section];默认实现走 extract_sections
ParseFn = Callable[[Path, str], list[Section]]


def _default_parse(path: Path, ext: str) -> list[Section]:
    return extract_sections(path, ext)


class DocWorker:
    def __init__(
        self,
        store: DocStore,
        bus: EventBus | None,
        queue: asyncio.Queue,
        workspace: Path,
        *,
        parse_fn: ParseFn | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._queue = queue
        self._parse = parse_fn or _default_parse
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            item = await self._queue.get()
            # 解析任务为 str(doc_id);删除任务为 ("remove", doc_id, local_path)
            try:
                if isinstance(item, tuple) and item[0] == "remove":
                    await self._run_remove(item[1], item[2])
                else:
                    await self._run_one(item)
            except Exception as exc:  # noqa: BLE001  # worker 不能因单条任务死亡
                import logging
                logging.getLogger("sources.doc.worker").warning(
                    "worker 任务失败: item=%r error=%s", item, exc, exc_info=True)

    async def _run_remove(self, did: str, local_path: str) -> None:
        if not local_path:
            return
        path = Path(local_path)
        # 路径仍关联到被删文档记录才执行删除;同名再导入后新记录已指向新路径
        doc = self._store.get(did)
        if doc is not None and doc.get("local_path") == local_path:
            return
        try:
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
        except (OSError, PermissionError):
            # 文件占用等场景本次跳过,由记录移除后的无引用状态自然可复写/重解析
            pass

    async def _run_one(self, did: str) -> None:
        doc = self._store.get(did)
        if doc is None:
            return
        await self._emit("task.progress", did, kind="doc", progress=0.1,
                         stage="parse")
        loop = asyncio.get_running_loop()
        try:
            # 提取是 CPU/IO 混合密集体:进线程池,事件循环保持响应
            sections = await loop.run_in_executor(
                None, self._parse, Path(doc["local_path"]), doc["ext"])
            payload = [{"section_no": s.section_no, "title": s.title,
                        "page_start": s.page_start, "page_end": s.page_end,
                        "text": s.text} for s in sections]
            self._store.replace_sections(did, payload)
            self._store.set_status(did, "ready")
            for i, s in enumerate(sections):
                await self._emit("task.progress", did, kind="doc",
                                 progress=(i + 1) / len(sections), stage="parse")
            await self._emit("source.ready", did, kind="doc", title=doc["title"],
                             sections=len(sections))
        except ExtractError as exc:
            self._store.set_status(did, "failed", error=str(exc)[:500])
            await self._emit("task.failed", did, kind="doc", error=str(exc)[:300])
        except Exception as exc:  # noqa: BLE001  # 失败落库,不拖垮 worker
            self._store.set_status(did, "failed",
                                   error=f"解析异常: {exc}"[:500])
            await self._emit("task.failed", did, kind="doc",
                             error=f"解析异常: {exc}"[:300])

    async def _emit(self, type_: str, did: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(type=type_, actor=_ACTOR, payload={"source_id": did, **payload})
            )
