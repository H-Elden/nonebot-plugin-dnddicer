"""示例时间线回归测试：转录必须与 baseline/ 逐字一致。

- 整条时间线在一次运行里顺序执行（跨场景状态延续），逐场景与基线文件比对；
- 基线由 doc/tools/render-docs-examples.py --write-baseline 生成（不入库工具），
  插件文案或行为改变时本测试失败，提示同步更新基线**与 docs/ 页面**；
- 本模块走真实群聊服务门禁（``service_gate`` 标记），不使用 conftest 的旁路，
  场景内部的 bypass 由 harness 自己按步控制。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scenarios
from harness import TimelineRunner
from transcript import render_scene

BASELINE_DIR = Path(__file__).resolve().parent / "baseline"

pytestmark = pytest.mark.service_gate


@pytest.mark.asyncio
async def test_timeline_matches_baseline() -> None:
    runner = TimelineRunner()
    await runner.reset_group_state()

    for scene in scenarios.TIMELINE:
        lines = await runner.run_scene(scene)
        assert lines, f"场景 {scene.id} 没有产生任何消息"

        baseline_path = BASELINE_DIR / f"{scene.id}.txt"
        assert baseline_path.exists(), (
            f"缺少基线文件 {baseline_path.name}；"
            "请运行 .venv/Scripts/python.exe doc/tools/render-docs-examples.py --write-baseline"
        )
        expected = baseline_path.read_text(encoding="utf-8")
        actual = render_scene(scene.id, scene.title, lines)
        assert actual == expected, (
            f"场景 {scene.id} 的转录与基线不一致；"
            "若为插件文案变更，请更新基线并同步 docs/ 页面"
        )
