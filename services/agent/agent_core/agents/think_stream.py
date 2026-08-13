"""
流式解析「思考 / 正文」双通道。

模型约定输出：
  <<<THINK>>>
  ...推理...
  <<<END_THINK>>>
  正文 Markdown...

未使用标记时：全部视为正文（兼容旧行为）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

THINK_START = "<<<THINK>>>"
THINK_END = "<<<END_THINK>>>"


def _is_partial_marker(buf: str) -> bool:
    """缓冲是否可能为 THINK_START 的未完成前缀（继续等待更多 token 再判定）。"""
    s = buf.lstrip()
    if not s:
        return True  # 纯空白：仍需等待
    if len(s) >= len(THINK_START):
        return False
    # s 以 THINK_START 的某个前缀开头（例如只收到 "<"）→ 可能是标记开头
    return any(THINK_START.startswith(s[:i]) for i in range(1, len(s) + 1))


@dataclass
class ThinkStreamSplitter:
    """增量喂入 token，产出 (channel, text) 片段。channel: thinking | text"""

    _buf: str = ""
    _mode: str = "detect"  # detect | thinking | text
    _emitted_any_text: bool = False
    events: list[tuple[str, str]] = field(default_factory=list)

    def feed(self, piece: str) -> list[tuple[str, str]]:
        if not piece:
            return []
        self._buf += piece
        out: list[tuple[str, str]] = []

        while True:
            if self._mode == "detect":
                # 跳过开头空白，判断是否以 THINK 开头
                stripped_l = self._buf.lstrip()
                if _is_partial_marker(stripped_l):
                    # 可能仍在匹配起始标记，继续缓冲
                    break
                if stripped_l.startswith(THINK_START):
                    # 丢弃起始标记前空白 + 标记本身
                    idx = self._buf.find(THINK_START)
                    self._buf = self._buf[idx + len(THINK_START) :]
                    self._mode = "thinking"
                    continue
                # 无标记：整段当正文
                if self._buf:
                    # 若缓冲可能是标记前缀的一部分（例如 "<"），再等等
                    if _is_partial_marker(self._buf):
                        break
                    out.append(("text", self._buf))
                    self._emitted_any_text = True
                    self._buf = ""
                    self._mode = "text"
                break

            if self._mode == "thinking":
                end = self._buf.find(THINK_END)
                if end < 0:
                    # 保留可能构成 END 标记的后缀
                    keep = len(THINK_END) - 1
                    if len(self._buf) > keep:
                        emit = self._buf[:-keep]
                        self._buf = self._buf[-keep:]
                        if emit:
                            out.append(("thinking", emit))
                    break
                think_part = self._buf[:end]
                if think_part:
                    out.append(("thinking", think_part))
                self._buf = self._buf[end + len(THINK_END) :]
                # 去掉 END 后的一个换行
                if self._buf.startswith("\r\n"):
                    self._buf = self._buf[2:]
                elif self._buf.startswith("\n"):
                    self._buf = self._buf[1:]
                self._mode = "text"
                continue

            # text mode
            if self._buf:
                out.append(("text", self._buf))
                self._emitted_any_text = True
                self._buf = ""
            break

        return out

    def flush(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self._buf:
            return out
        if self._mode == "thinking":
            out.append(("thinking", self._buf))
        else:
            out.append(("text", self._buf))
            self._emitted_any_text = True
        self._buf = ""
        return out


def split_complete_text(text: str) -> tuple[str, str]:
    """非流式：拆成 (thinking, body)。"""
    if not text:
        return "", ""
    s = text.lstrip()
    if not s.startswith(THINK_START):
        return "", text
    rest = s[len(THINK_START) :]
    end = rest.find(THINK_END)
    if end < 0:
        # 未闭合 THINK：整段当正文，避免「思考有货、气泡空白」
        return "", rest.strip()
    thinking = rest[:end].strip()
    body = rest[end + len(THINK_END) :].lstrip("\r\n")
    return thinking, body


THINK_FORMAT_HINT = (
    "输出格式（必须遵守）：\n"
    "1) 先写简短推理（3-8 句），用标记包裹：\n"
    f"{THINK_START}\n"
    "（推理要点，不要写最终结论全文）\n"
    f"{THINK_END}\n"
    "2) 标记结束后直接输出给用户的正文 Markdown。\n"
    "禁止 emoji。不要省略标记。"
)
