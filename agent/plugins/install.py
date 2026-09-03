"""插件安装原语(phase-77,§9.13):zip 安全解压、目录源校验、落盘。

只做文件搬运的纯原语,不含发现/批准语义(在 manager);声明式 only——
绝不执行插件内任何脚本,也没有 post-install 钩子。

选型(写回钉死):
- zip 根约定:zip 根下直接有 plugin.json → 根即插件根;否则「恰一个顶层目录
  且其下有 plugin.json」→ 该目录即插件根(忽略 __MACOSX 与顶层点开头目录的
  打包垃圾);0 个或多个候选一律拒,禁止猜。
- 限额:zip ≤ 20 MiB(目录源总量同限)、文件数 ≤ 500、单文件 ≤ 5 MiB;
  超限 INVALID_INPUT,整包拒绝不落盘。zip bomb 由「文件数 × 单文件」双限兜住。
- zip slip:每个成员名禁 `..` 段 / 绝对路径 / 盘符 / 反斜杠 / NUL,且逐条
  resolve 后须仍在解压根内;违规整包中止。解压只发生在系统临时目录,
  校验全过前 plugins/ 不会有任何内容。Windows 目录联接(junction)不被
  is_symlink 识别(内容只流入 plugins/ 不外流,写回披露)。
- 符号链接:zip 解压按普通文件写(Python zipfile 不产生链接);目录源内
  任何符号链接(文件或目录)一律拒——防止把 root 外内容拷进 plugins/。
- 落盘:copytree 到 plugins/<name>/;失败由调用方清半截目录(B3)。
  临时解压区用 tempfile(系统临时区),装完即删,runtime-data 不留副本。
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from platform_contracts import ErrorSuffix, ServiceError

#: zip 体积 / 目录源总量上限(A4;可调,测试经 monkeypatch 钉行为)
MAX_ZIP_BYTES = 20 * 1024 * 1024
#: 解压 / 复制后单文件上限
MAX_FILE_BYTES = 5 * 1024 * 1024
#: 文件数上限
MAX_FILES = 500

#: 插件名直接作目录名拼进路径:目录名安全字符 + Windows 保留名拒(允许 `_` 前缀,
#: 与 discover 语义一致;见 safe_plugin_name)
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_NAME_MAX_LEN = 64
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _invalid(message: str) -> ServiceError:
    return ServiceError("agent", ErrorSuffix.INVALID_INPUT, message)


def safe_plugin_name(name: str) -> str:
    """manifest.name 校验为可用目标目录名(A5):非空、≤64、安全字符、非保留名。

    允许 `_` 前缀(与 discover 一致);非法即拒安装,不猜目录名。
    """
    text = name.strip()
    if (
        not text or len(text) > _NAME_MAX_LEN or not _NAME_RE.match(text)
        or text.upper() in _WINDOWS_RESERVED
    ):
        raise _invalid(f"插件名不能用作安装目录名(≤64 字符,字母数字 _ . -): {name!r}")
    return text


def _member_dest(root: Path, arcname: str) -> Path | None:
    """zip 成员名 → 解压目标绝对路径;不安全(A2 zip slip)→ None。"""
    if not arcname or "\\" in arcname or "\x00" in arcname:
        return None
    pure = PurePosixPath(arcname)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        return None
    if len(arcname) > 1 and arcname[1] == ":":  # Windows 盘符(C:/…)
        return None
    target = (root / arcname).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _locate_plugin_root(extract_root: Path) -> Path:
    """zip 根约定(B5,选型钉死):根即插件根,或恰一个含 plugin.json 的顶层目录。"""
    if (extract_root / "plugin.json").is_file():
        return extract_root
    top_dirs = [
        p for p in extract_root.iterdir()
        if p.is_dir() and p.name != "__MACOSX" and not p.name.startswith(".")
    ]
    if len(top_dirs) == 1 and (top_dirs[0] / "plugin.json").is_file():
        return top_dirs[0]
    raise _invalid(
        "zip 里找不到唯一的 plugin.json(约定:zip 根即插件根,"
        "或恰有一个含 plugin.json 的顶层目录)"
    )


def extract_plugin_zip(zip_path: Path, tmp: Path) -> Path:
    """zip 解压到 tmp(系统临时区):逐成员校验路径安全与限额,返回插件根。

    任何违规整包拒;plugins/ 目录在本函数里完全不被触碰(B3/A2:先解压校验,
    后由调用方落盘)。
    """
    try:
        size = zip_path.stat().st_size
    except OSError as exc:
        raise _invalid(f"读不到 zip 文件: {exc}") from exc
    if size > MAX_ZIP_BYTES:
        raise _invalid(f"zip 超过 {MAX_ZIP_BYTES // (1024 * 1024)} MiB 上限")
    extract_root = tmp / "unpacked"
    extract_root.mkdir(parents=True, exist_ok=True)  # 空 zip 也要有根可定位
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _invalid(f"不是有效的 zip 文件: {exc}") from exc
    with archive:
        members = [i for i in archive.infolist() if not i.is_dir()]
        if len(members) > MAX_FILES:
            raise _invalid(f"zip 内文件数超过 {MAX_FILES} 上限")
        for info in members:
            target = _member_dest(extract_root, info.filename)
            if target is None:
                raise _invalid(f"zip 含不安全路径条目(如 ../ 或绝对路径),整包拒绝: "
                               f"{info.filename!r}")
            try:
                with archive.open(info) as f:
                    data = f.read(MAX_FILE_BYTES + 1)
            except RuntimeError as exc:  # 加密 zip:zipfile 抛 RuntimeError
                raise _invalid("zip 已加密,不支持安装") from exc
            if len(data) > MAX_FILE_BYTES:
                raise _invalid(
                    f"单文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MiB 上限: "
                    f"{info.filename!r}"
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:  # 路径过深 / 盘满等,给可读消息而非 INTERNAL
                raise _invalid(f"写入解压条目失败: {info.filename!r}: {exc}") from exc
    return _locate_plugin_root(extract_root)


def prepare_source_dir(src: Path) -> Path:
    """目录安装源校验(B4):真实存在、无符号链接、限额之内;返回源路径。"""
    if not src.is_dir():
        raise _invalid(f"插件源目录不存在或不是目录: {src}")
    files: list[Path] = []
    for base, dirs, names in os.walk(src, followlinks=False):
        here = Path(base)
        for d in dirs:
            if (here / d).is_symlink():
                raise ServiceError("agent", ErrorSuffix.FORBIDDEN,
                                   f"源目录含符号链接,拒绝安装: {d}")
        for n in names:
            fp = here / n
            if fp.is_symlink():
                raise ServiceError("agent", ErrorSuffix.FORBIDDEN,
                                   f"源目录含符号链接,拒绝安装: {n}")
            files.append(fp)
    if len(files) > MAX_FILES:
        raise _invalid(f"源目录文件数超过 {MAX_FILES} 上限")
    total = 0
    for fp in files:
        size = fp.stat().st_size
        if size > MAX_FILE_BYTES:
            raise _invalid(
                f"单文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MiB 上限: "
                f"{fp.relative_to(src)}"
            )
        total += size
    if total > MAX_ZIP_BYTES:
        raise _invalid(f"源目录总量超过 {MAX_ZIP_BYTES // (1024 * 1024)} MiB 上限")
    return src


def place_plugin(src: Path, dest: Path) -> None:
    """把校验过的插件根复制到 plugins/<name>/(B4 复制非移动;dest 须不存在)。"""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
