"""文档比对：docs/ 页面里的气泡示例必须能追溯到 baseline 转录（禁止手编）。

规则（与 `::: chat` 容器语法一致）：

- 一个气泡块内部，逐条消息按顺序在时间线里**单调递增**地匹配「昵称 + 正文逐字一致」；
  匹配不上即失败（说明该示例不是真实运行产出，或转录已过期）；
- 页面上出现的昵称必须属于「骰娘系 ∪ 示例团名册」（新增人物时要同时更新 cast 与容器名册）；
- `注：` 行是讲解条，不参与比对。

范围控制：``SYNCED_PAGES`` 覆盖站点里含气泡示例的页面（新增页面时把相对路径登记进去即可；
由 CHANGELOG.md 生成的 ``guide/changelog.md`` 没有示例、不在此列）。新增场景后先跑
``doc/tools/render-docs-examples.py --write-baseline`` 更新基线，再写页面。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import cast
import scenarios
from transcript import Line, parse_messages

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
BASELINE_DIR = Path(__file__).resolve().parent / "baseline"

#: 纳入比对的页面（已覆盖全部站点页面；新增页面时在此登记）
SYNCED_PAGES = [
    "guide/cast.md",
    "guide/quickstart.md",
    "guide/roll-basics.md",
    "guide/roll-advanced.md",
    "guide/initiative.md",
    "guide/character-card.md",
    "guide/checks.md",
    "guide/weapons.md",
    "guide/hp-rest.md",
    "guide/battle.md",
    "guide/dm-guide.md",
    "guide/overview.md",
    "guide/faq.md",
]

_OPEN_PATTERN = re.compile(r"^:::\s*chat\s*$")
_CLOSE_PATTERN = re.compile(r"^:::\s*$")


def _load_timeline() -> List[Line]:
    """按时间线顺序读取全部基线转录。"""
    timeline: List[Line] = []
    for scene in scenarios.TIMELINE:
        path = BASELINE_DIR / f"{scene.id}.txt"
        assert path.exists(), (
            f"缺少基线文件 {path.name}；"
            "请运行 .venv/Scripts/python.exe doc/tools/render-docs-examples.py --write-baseline"
        )
        timeline.extend(parse_messages(path.read_text(encoding="utf-8")))
    return timeline


def _extract_chat_blocks(page_text: str) -> List[str]:
    """抽出页面里全部 `::: chat` 容器的正文。"""
    blocks: List[str] = []
    current: List[str] | None = None
    for raw in page_text.split("\n"):
        line = raw.strip()
        if current is None:
            if _OPEN_PATTERN.match(line):
                current = []
            continue
        if _CLOSE_PATTERN.match(line):
            blocks.append("\n".join(current))
            current = None
            continue
        current.append(raw)
    return blocks


def test_docs_examples_are_traceable() -> None:
    """已重写页面的每条示例消息都能在时间线里按序找到。"""
    timeline = _load_timeline()
    allowed_speakers = {cast.BOT_NAME, cast.PRIVATE_BOT_NAME} | set(cast.BY_NAME)

    problems: List[str] = []
    for relative in SYNCED_PAGES:
        page = DOCS_DIR / relative
        assert page.exists(), f"SYNCED_PAGES 中的页面不存在：{relative}"

        blocks = _extract_chat_blocks(page.read_text(encoding="utf-8"))
        assert blocks, f"{relative} 里没有找到任何 ::: chat 块"

        for index, block in enumerate(blocks, start=1):
            cursor = 0
            for message in parse_messages(block):
                if message.speaker not in allowed_speakers:
                    problems.append(
                        f"{relative} 第 {index} 个气泡块：昵称「{message.speaker}」"
                        "不在骰娘/示例团名册内（新人物需同步 cast.py 与容器名册）"
                    )
                    continue

                found = None
                for position in range(cursor, len(timeline)):
                    candidate = timeline[position]
                    if (
                        candidate.speaker == message.speaker
                        and candidate.text == message.text
                    ):
                        found = position
                        break

                if found is None:
                    first_line = message.text.split("\n")[0]
                    problems.append(
                        f"{relative} 第 {index} 个气泡块：找不到真实来源——"
                        f"「{message.speaker} | {first_line}」"
                        "（示例需取自 baseline 转录，先加场景并重新生成基线）"
                    )
                else:
                    cursor = found + 1

    assert not problems, "\n".join(problems)
