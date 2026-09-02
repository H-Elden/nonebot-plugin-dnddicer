# ---------------------------------------------------------------------------
# 本目录结构移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# Ported from nonebot-dicepp — 本包仅保留掷骰引擎所需依赖子集
# （DicePP 原 module/roll/ 还含大量命令模块，DNDDicer 不迁移，业务层自研）。
# ---------------------------------------------------------------------------

"""掷骰引擎依赖（nonebot-dicepp ``module/roll/`` 的引擎用子集）。

仅包含引擎依赖的纯逻辑文件：``result`` / ``roll_utils`` / ``roll_config`` /
``roll_const`` / ``karma_runtime``（可选掷骰运行时注入点，默认 None）/
``sequence_runtime``（固定序列骰子，供确定性测试）/ ``_string_utils``。
"""

from .result import RollResult
from .roll_utils import RollDiceError

__all__ = ["RollResult", "RollDiceError"]
