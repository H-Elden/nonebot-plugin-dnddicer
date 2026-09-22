"""转录文本：与站点 `::: chat` 容器同语法的序列化与解析。

- 序列化：一个场景 → ``# 场景：<id> · <标题>`` + 逐条 ``昵称 | 内容``；多行消息的
  后续行原样输出（与容器的「续行」规则一致）；私聊的发言人写作「屠龙骰（私聊）」。
- 解析：把容器正文（或转录文本）拆成消息行序列，供文档比对测试使用；
  ``注：`` 行是讲解条、不属于骰娘输出，解析时忽略。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

#: 与 chat-container.mts 里的 MESSAGE_PATTERN 保持一致（昵称不含 | [ ] = 且较短）
_MESSAGE_PATTERN = re.compile(r"^([^|=[\]]{1,24}?)\s*\|\s+(.*)$")
#: 注释行（半角/全角冒号均可）
_NOTE_PATTERN = re.compile(r"^注[:：]\s*(.*)$")
#: 转录文件头（场景声明行）
_HEADER_PATTERN = re.compile(r"^#\s*场景[:：]\s*([^\s·]+)\s*(?:·\s*(.*))?$")


@dataclass
class Line:
    """一条消息：发言人 + 正文（可多行）。"""

    speaker: str
    text: str

    def render(self) -> List[str]:
        """渲染为转录行（首行带发言人，其余为续行）。"""
        body = self.text.split("\n")
        return [f"{self.speaker} | {body[0]}", *body[1:]]


def render_scene(scene_id: str, title: str, lines: List[Line]) -> str:
    """序列化一个场景的转录（含表头，末行换行）。"""
    rendered: List[str] = [f"# 场景：{scene_id} · {title}", ""]
    for line in lines:
        rendered.extend(line.render())
    return "\n".join(rendered) + "\n"


def parse_header(source: str) -> Optional[tuple[str, str]]:
    """读取转录文件头，返回 ``(场景 id, 标题)``；没有头部时返回 None。"""
    for raw in source.split("\n"):
        stripped = raw.strip()
        if not stripped:
            continue
        match = _HEADER_PATTERN.match(stripped)
        if match:
            return match.group(1), (match.group(2) or "").strip()
        return None
    return None


def parse_messages(source: str) -> List[Line]:
    """解析容器正文 / 转录正文为消息行（``注：`` 行忽略，续行并入上一条消息）。"""
    lines: List[Line] = []
    current: Optional[Line] = None
    previous_blank = True
    for raw in source.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            previous_blank = True
            continue
        # `注：` 行须自成一段（与容器规则一致）；紧随消息出现的按续行处理
        if previous_blank and _NOTE_PATTERN.match(line):
            current = None
            previous_blank = False
            continue
        previous_blank = False

        match = _MESSAGE_PATTERN.match(line)
        if match:
            current = Line(match.group(1).strip(), match.group(2))
            lines.append(current)
            continue
        if current is not None:
            current.text += "\n" + line
    return lines
