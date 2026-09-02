# ---------------------------------------------------------------------------
# 本文件移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# Ported from nonebot-dicepp — 自上游 utils/string.py 裁剪，仅保留掷骰引擎
# 使用的 to_english_str()；逻辑语义与上游一致，不做改动。
# ---------------------------------------------------------------------------

"""字符串工具（上游 nonebot-dicepp utils/string.py 的引擎用子集）。

供 engine/roll/ast_engine/preprocessor.py 做全角→半角转换。
"""


def to_english_str(input_str: str) -> str:
    """
    将字符串中的中文符号与全角字符转为英文
    """
    if type(input_str) != str:
        raise ValueError(f'ChineseToEnglishSymbol: Input {input_str} must be str type')
    output_str = ""
    for character in input_str:
        code: int = ord(character)
        if code == 12288: # 全角空格 变 普通空格
            code = 32
        elif code == 12290: # 中文句号 变 英文句号
            code = 46
        elif code >= 65281 and code <= 65374: # 剩下的全角火星文全部位移回半角
            code -= 65248
        output_str += chr(code)
    """
    。，＋－＝＃：；（）ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｙｗｘｙｚ等
    """
    return output_str
