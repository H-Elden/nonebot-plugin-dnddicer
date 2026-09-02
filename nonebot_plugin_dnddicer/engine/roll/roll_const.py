# ---------------------------------------------------------------------------
# 本文件移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# Ported from nonebot-dicepp — 逻辑语义与上游一致，仅做 import/路径适配；
# 改动记录见移植说明文件头注释。
# ---------------------------------------------------------------------------
"""
roll_const.py — roll 模块共享常量

将跨文件引用的常量集中在此处，避免重复定义导致语义漂移。
"""

#: 多轮掷骰上限次数（`#` 或 BAB 推导结果超出此值则回退为 1）
MULTI_ROLL_LIMIT: int = 10
