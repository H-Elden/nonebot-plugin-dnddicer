# ---------------------------------------------------------------------------
# 本目录移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# ---------------------------------------------------------------------------

"""掷骰引擎依赖（仅保留掷骰引擎所需的纯逻辑子集）。

包含：``result`` / ``roll_utils`` / ``roll_config`` /
``roll_const`` / ``karma_runtime``（可选掷骰运行时注入点，默认 None）/
``sequence_runtime``（固定序列骰子，供确定性测试）/ ``_string_utils``。
"""

from .result import RollResult
from .roll_utils import RollDiceError

__all__ = ["RollResult", "RollDiceError"]
