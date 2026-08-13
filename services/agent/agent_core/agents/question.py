"""ask_user 结果规范化 —— 从工具输出构建前端 AgentQuestion 结构"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any


def _clean_options(raw: Any) -> list[dict[str, str]]:
    """过滤空选项；兼容字符串/字母键字典/JSON；拒绝字符串被逐字拆开。"""
    list_raw: list[Any] = []
    if isinstance(raw, str):
        t = raw.strip()
        # 优先按 A/B/C 行解析
        letter_opts = _parse_letter_options(t)
        if len(letter_opts) >= 2:
            return letter_opts
        if t.startswith("["):
            try:
                parsed = json.loads(t)
                if isinstance(parsed, list):
                    list_raw = parsed
            except json.JSONDecodeError:
                list_raw = [x.strip() for x in re.split(r"[,，;；|]", t) if x.strip()]
        elif "\n" in t:
            list_raw = [x.strip() for x in t.split("\n") if x.strip()]
        elif t:
            list_raw = [x.strip() for x in re.split(r"[,，;；|]", t) if x.strip()]
    elif isinstance(raw, list):
        # 防护：list("abc") → ['a','b','c']；保留合法的 ['A','B','C']
        if (
            len(raw) >= 2
            and all(isinstance(x, str) and len(x) <= 1 for x in raw)
            and not all(
                isinstance(x, str) and re.match(r"^[A-Da-d]$", x) for x in raw
            )
        ):
            list_raw = []
        else:
            list_raw = raw
    elif isinstance(raw, dict):
        items = list(raw.items())
        if len(items) >= 2 and all(
            str(k).isdigit() and isinstance(v, str) and len(v) <= 1
            for k, v in items
        ):
            list_raw = []
        else:
            list_raw = [{"value": k, "label": v} for k, v in items]

    out: list[dict[str, str]] = []
    for o in list_raw:
        if o is None:
            continue
        if isinstance(o, (str, int, float)):
            s = str(o).strip()
            if not s:
                continue
            m = re.match(r"^([A-Da-d])[.、)）：:\s]+\s*(.+)$", s)
            if m:
                letter = m.group(1).upper()
                out.append({"value": letter, "label": f"{letter}. {m.group(2).strip()}"})
            else:
                out.append({"value": s, "label": s})
            continue
        if isinstance(o, (list, tuple)) and len(o) >= 2:
            letter = str(o[0]).strip()
            label = str(o[1]).strip()
            if label:
                if re.match(r"^[A-Da-d]$", letter):
                    out.append(
                        {
                            "value": letter.upper(),
                            "label": f"{letter.upper()}. {label}",
                        }
                    )
                else:
                    out.append({"value": letter, "label": label})
            continue
        if isinstance(o, dict):
            label = str(
                o.get("label")
                or o.get("text")
                or o.get("name")
                or o.get("content")
                or o.get("desc")
                or o.get("description")
                or o.get("answer")
                or o.get("option")
                or o.get("choice")
                or o.get("body")
                or ""
            ).strip()
            value = str(o.get("value") or o.get("id") or o.get("key") or "").strip()
            if (not label or (re.match(r"^[A-Da-d]$", label) and label == value)) and o.get(
                "description"
            ):
                label = str(o.get("description") or "").strip()
            if not label and not value:
                # 单键 {"A": "文案"} 或过滤 correct 后仅剩一键
                pairs = [
                    (k, v)
                    for k, v in o.items()
                    if k not in ("correct", "is_correct", "score")
                ]
                if len(pairs) == 1:
                    k, v = pairs[0]
                    value = str(k).strip()
                    label = str(v).strip()
            if not label and value:
                label = value
            if not value and label:
                value = label
            if not label and not value:
                continue
            # 纯题号无正文 → 跳过（交给题干解析 / 文本兜底）
            if re.match(r"^[A-Da-d]$", label) and label == value:
                continue
            # 丢弃无意义单字符（非 A-D 题号）
            if len(label) <= 1 and not re.match(r"^[A-Da-d]$", label):
                continue
            item: dict[str, str] = {"value": value, "label": label}
            desc = o.get("description")
            if desc and str(desc).strip() != label:
                item["description"] = str(desc)
            out.append(item)

    # 再防一层：多数选项仍是单字符 → 视为损坏
    if len(out) >= 2:
        short = sum(1 for x in out if len(x.get("label") or "") <= 1)
        if short >= max(2, (len(out) + 1) // 2):
            return []
        # 假「选项 A」占位也视为损坏
        placeholders = sum(
            1
            for x in out
            if re.match(r"^选项\s*[A-Da-d]$", (x.get("label") or "").strip())
        )
        if placeholders >= min(2, len(out)):
            return []
    return out


def _parse_letter_options(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"(?:^|\n)\s*(?:[-*•]\s*)?(?:\*\*)?([A-Da-d])(?:\*\*)?[.、)）：:]\s*(.+?)(?=(?:\n\s*(?:[-*•]\s*)?(?:\*\*)?[A-Da-d](?:\*\*)?[.、)）：:])|\n\n|$)",
        text,
        flags=re.S,
    ):
        letter = m.group(1).upper()
        label = re.sub(r"\*\*", "", m.group(2)).strip()
        if not label or letter in seen:
            continue
        # 跳过假占位
        if re.match(r"^选项\s*[A-Da-d]$", label):
            continue
        seen.add(letter)
        out.append({"value": letter, "label": f"{letter}. {label}"})
    return out


def _default_options(qid_item: str, prompt: str) -> list[dict[str, str]]:
    key = f"{qid_item} {prompt}".lower()
    if any(k in key for k in ("水平", "level", "掌握", "熟练", "程度")):
        return [
            {"value": "beginner", "label": "初学 · 刚接触"},
            {"value": "intermediate", "label": "了解 · 能读简单代码"},
            {"value": "advanced", "label": "掌握 · 能独立改功能"},
            {"value": "expert", "label": "精通 · 能讲架构与设计"},
        ]
    if any(k in key for k in ("语言", "language", "tech", "技术栈", "想学")):
        return [
            {"value": "python", "label": "Python"},
            {"value": "typescript", "label": "TypeScript / JavaScript"},
            {"value": "go", "label": "Go"},
            {"value": "rust", "label": "Rust"},
            {"value": "cpp", "label": "C / C++"},
            {"value": "other", "label": "其他（下方填写）"},
        ]
    if any(k in key for k in ("想做", "目标", "goal", "这次", "目的")):
        return [
            {"value": "overview", "label": "快速了解某个项目"},
            {"value": "learn", "label": "系统学习 / 跟读源码"},
            {"value": "path", "label": "规划学习路径"},
            {"value": "compare", "label": "对比多个项目"},
        ]
    # 测验类禁止假「选项 A」——返回空，由上层改成可填写
    return []


def _normalize_question(tool_result: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
    """将 ask_user 工具结果转为前端 AgentQuestion 结构。"""
    qid = f"q_{uuid.uuid4().hex[:12]}"
    title = tool_result.get("title") or "请回答以下问题"
    items = tool_result.get("items") or []
    questions: list[dict[str, Any]] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        qtype = it.get("type") or "single_choice"
        qid_item = it.get("id") or f"item_{len(questions)}"
        prompt = it.get("prompt") or it.get("text") or "请选择"
        options = it.get("options") or it.get("choices") or it.get("answers") or []
        if qtype in ("single_choice", "radio", "quiz"):
            opt_list = _clean_options(options)
            if len(opt_list) < 2:
                opt_list = _parse_letter_options(str(prompt))
            if len(opt_list) < 2:
                opt_list = _default_options(str(qid_item), str(prompt))
            exam = qtype == "quiz" or bool(
                re.search(r"测验|考试|小测试|考考你|掌握度|第\s*\d+\s*题", f"{prompt} {title}")
            )
            if len(opt_list) < 2:
                questions.append(
                    {
                        "id": qid_item,
                        "text": f"{prompt}\n\n（选项未能解析，请直接填写你的答案）",
                        "type": "radio",
                        "options": [
                            {"value": "other", "label": "自由填写（下方输入）"}
                        ],
                        "allow_other": True,
                        "exam": False,
                    }
                )
            else:
                questions.append(
                    {
                        "id": qid_item,
                        "text": prompt,
                        "type": "radio",
                        "options": opt_list,
                        "allow_other": not exam,
                        "exam": exam,
                    }
                )
        elif qtype in ("multi_choice", "checkbox"):
            opt_list = _clean_options(options)
            if len(opt_list) < 2:
                opt_list = _parse_letter_options(str(prompt))
            if len(opt_list) < 2:
                opt_list = _default_options(str(qid_item), str(prompt))
            questions.append(
                {
                    "id": qid_item,
                    "text": prompt,
                    "type": "checkbox",
                    "options": [
                        {"value": o["value"], "text": o["label"]} for o in opt_list
                    ],
                }
            )
        elif qtype in ("scale", "slider"):
            questions.append(
                {
                    "id": qid_item,
                    "text": prompt,
                    "type": "slider",
                    "min": int(it.get("min", 0)),
                    "max": int(it.get("max", 100)),
                    "labels": it.get("labels") or {"0": "不懂", "100": "精通"},
                }
            )
        else:
            # text → 短答用滑块式自由填写入口
            questions.append(
                {
                    "id": qid_item,
                    "text": prompt,
                    "type": "radio",
                    "options": [{"value": "other", "label": "自由填写（下方输入）"}],
                    "allow_other": True,
                }
            )
    if not questions:
        # 禁止把面板标题当成题干（否则出现 Q1=「请回答以下问题」）
        questions.append(
            {
                "id": "default",
                "text": "你的编程 / 技术掌握水平大致处于哪个阶段？",
                "type": "radio",
                "options": _default_options("level", "水平"),
                "allow_other": True,
            }
        )
    else:
        # 题干缺失或与标题撞车时，按选项语义补一句真正的问题
        generic = {"请回答以下问题", "请选择", "请选择最符合的一项", ""}
        title_s = str(title or "").strip()
        for q in questions:
            text = str(q.get("text") or "").strip()
            if text and text not in generic and text != title_s:
                continue
            labels = " ".join(
                str((o.get("label") if isinstance(o, dict) else o) or "")
                for o in (q.get("options") or [])
            )
            if any(k in labels for k in ("初学", "了解", "掌握", "精通")):
                q["text"] = "你的编程 / 技术掌握水平大致处于哪个阶段？"
            elif any(k in labels for k in ("Python", "TypeScript", "Go", "Rust")):
                q["text"] = "你更熟悉 / 想用哪一类技术栈？"
            elif text in generic or text == title_s:
                q["text"] = "请选择最符合你情况的一项："
    return {
        "question_id": qid,
        "agent_id": agent_id,
        "intro": {"type": "markdown", "content": f"**{title}**"},
        "questions": questions,
        "actions": {
            "submit": {"text": "提交", "style": "primary"},
            "skip": {"text": "跳过", "style": "ghost"},
        },
        "allow_skip": bool(tool_result.get("allow_skip", True)),
        "timeout": None,
    }
