# ---------------------------------------------------------------------------
# 本目录结构移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# Ported from nonebot-dicepp — 引擎包结构与上游 module/roll/ 保持一致，
# 仅裁剪出掷骰引擎所需的子集（不含任何 DicePP 命令/业务层）。
# ---------------------------------------------------------------------------

"""掷骰引擎（DNDDicer 引擎层）。

结构说明（镜像 nonebot-dicepp ``module/roll/`` 的包层次，使引擎文件的相对导入
零改动、便于同步上游）：

- ``roll/ast_engine/``  掷骰表达式引擎：Lark 文法解析器（parser）、强类型 AST
  （ast_nodes）、求值器（evaluator）、过程 trace（trace）、错误模型（errors）、
  安全限制（limits）、全角/中文别名预处理（preprocessor）、对外 API（adapter）；
- ``roll/``             引擎依赖：result（RollResult）、roll_utils（掷骰工具）、
  roll_config / roll_const（常量）、karma_runtime（可选掷骰运行时注入点，
  默认 None = 普通随机，DNDDicer 不使用业力骰）、sequence_runtime（测试用
  固定序列骰子）、_string_utils（上游 utils/string 的全角转半角子集）。

引擎公共入口（业务层/命令层使用）：``exec_roll_exp_unified`` /
``exec_roll_exp_ast`` / ``is_roll_exp`` / ``sift_roll_exp_and_reason`` 等，
见 ``roll/ast_engine/__init__.py`` 的 ``__all__``。

约定：引擎文件为移植代码，改动需保持逻辑语义不变（仅 import/路径适配），
改动记录标注于文件头与各适配点注释；上游升级时按文件头记录做 diff 同步。
"""
