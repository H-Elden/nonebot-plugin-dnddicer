"""配置读取容错测试（2026-09-30）。

NoneBot 对**插件自定义配置项**统一做 JSON 解码（``json.loads`` 成功即采用解码
结果），于是 ``.env`` 里写数字（QQ 号 / 群号最自然的写法）到手就是 ``int``；
写 ``"12345678"`` 时外层引号也会先被 dotenv 剥掉、结果仍是 ``int``。而
pydantic v2 的 ``str`` 字段默认拒绝数字，曾直接导致整个插件加载失败（NoneBot
只记一行「Failed to import」，骰娘整体不响应）。

配置模型开了 ``coerce_numbers_to_str``，这里锁定「数字写法照常按文本读入」；
字符串写法与未配置的既有行为不变（分别由本文件与 ``tests/test_master_command.py``
/ ``tests/test_help_command.py`` 的命令级用例覆盖）。
"""

import json

from nonebot_plugin_dnddicer.config import Config


def test_numeric_master_fields_read_as_text() -> None:
    """三个骰主配置项写纯数字时按文本读入（模拟 NoneBot 的 JSON 解码链路）。"""
    config = Config(
        dnddicer_master_qq=json.loads("12345678"),
        dnddicer_master_contact=json.loads("12345678"),
        dnddicer_master_group=json.loads("87654321"),
    )
    assert config.dnddicer_master_qq == "12345678"
    assert config.dnddicer_master_contact == "12345678"
    assert config.dnddicer_master_group == "87654321"


def test_string_values_read_as_is() -> None:
    """字符串写法（含自由文本、带空格与引号的字体栈）照常读入，不受容错影响。"""
    config = Config(
        dnddicer_master_qq="10001",
        dnddicer_master_contact="QQ 12345678",
        dnddicer_master_group="87654321",
        dnddicer_query_image_font_family='"Noto Sans CJK SC", sans-serif',
    )
    assert config.dnddicer_master_qq == "10001"
    assert config.dnddicer_master_contact == "QQ 12345678"
    assert config.dnddicer_master_group == "87654321"
    assert config.dnddicer_query_image_font_family == '"Noto Sans CJK SC", sans-serif'


def test_numeric_values_accepted_for_all_text_fields() -> None:
    """容错是模型级开关：全部字符串字段都接受数字（字体家族同样放宽）。"""
    config = Config(
        dnddicer_master_qq=12345678,
        dnddicer_master_contact=12345678,
        dnddicer_master_group=87654321,
        dnddicer_query_image_font_family=123,
    )
    assert config.dnddicer_master_qq == "12345678"
    assert config.dnddicer_master_contact == "12345678"
    assert config.dnddicer_master_group == "87654321"
    assert config.dnddicer_query_image_font_family == "123"


def test_defaults_unchanged() -> None:
    """未配置时三个骰主字段仍为空串（零配置可加载不变）。"""
    config = Config()
    assert config.dnddicer_master_qq == ""
    assert config.dnddicer_master_contact == ""
    assert config.dnddicer_master_group == ""
