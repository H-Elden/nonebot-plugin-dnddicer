"""@ 提及目标基础层测试：@ 段标记化与带标记取参。

覆盖 platform/onebot_v11.py 的 @ 能力（重建文本 / 标记判定 / 真 @ 回复组装）
与 commands/base.py 的 get_command_rest_with_mentions（无 @ 时与既有取参一致）。
"""

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.commands import base
from nonebot_plugin_dnddicer.platform import onebot_v11


def _event(message: Message):
    """构造一条群消息事件（fake 事件 self_id=1，即机器人自身 QQ）。"""
    return fake_group_message_event_v11(message=message)


# =========================================================================
# @ 段标记化
# =========================================================================


def test_rebuild_text_keeps_mention_mark():
    """at 段重建为 @<qq> 标记，text 段原样拼接。"""
    event = _event(Message(".hp ") + MessageSegment.at(22222) + " -d4")
    assert onebot_v11.rebuild_text_with_mentions(event) == ".hp @22222 -d4"
    assert onebot_v11.list_mentions(event) == ["22222"]


def test_rebuild_text_multiple_mentions_in_order():
    """多个 @ 按消息顺序保留。"""
    event = _event(
        Message(".hp ")
        + MessageSegment.at(22222)
        + ";"
        + MessageSegment.at(33333)
        + " -d8"
    )
    assert onebot_v11.rebuild_text_with_mentions(event) == ".hp @22222;@33333 -d8"
    assert onebot_v11.list_mentions(event) == ["22222", "33333"]


def test_bot_self_mention_dropped():
    """机器人自身的 @ 与 @全体成员丢弃（@骰娘 .hp -d4 仍为给自己）。"""
    event = _event(Message(".hp ") + MessageSegment.at(1) + " -d4")
    assert onebot_v11.rebuild_text_with_mentions(event) == ".hp  -d4"
    assert onebot_v11.list_mentions(event) == []

    all_event = _event(Message(".hp ") + MessageSegment.at("all") + " -d4")
    assert onebot_v11.rebuild_text_with_mentions(all_event) == ".hp  -d4"
    assert onebot_v11.list_mentions(all_event) == []


def test_non_text_segments_ignored():
    """图片等非文本段与适配器 extract_plain_text 同语义：不进入重建文本。"""
    event = _event(Message(".hp -d4") + MessageSegment.image("file://x.png"))
    assert onebot_v11.rebuild_text_with_mentions(event) == ".hp -d4"
    assert onebot_v11.rebuild_text_with_mentions(event) == event.get_plaintext()


# =========================================================================
# 标记判定与解析
# =========================================================================


def test_mention_token_parse():
    """parse_mention_token 仅对完整标记生效。"""
    assert onebot_v11.parse_mention_token("@12345") == "12345"
    assert onebot_v11.parse_mention_token(" @12345 ") == "12345"
    assert onebot_v11.parse_mention_token("@12345易伤") is None
    assert onebot_v11.parse_mention_token("布兰克") is None
    assert onebot_v11.parse_mention_token("@abc") is None


def test_iter_and_strip_mentions():
    """iter_mentions 按序提取；strip_mentions 移除全部标记。"""
    assert onebot_v11.iter_mentions("a@1b@22") == ["1", "22"]
    assert onebot_v11.strip_mentions("@1易伤") == "易伤"
    assert onebot_v11.strip_mentions("+2 @1") == "+2 "


def test_strip_leading_mentions():
    """命令前的 @ 标记被剥离（先点名字再敲命令的输入习惯）。"""
    assert onebot_v11.strip_leading_mentions("@1 .hp -d4") == ".hp -d4"
    assert onebot_v11.strip_leading_mentions("@1 @2 .hp") == ".hp"
    assert onebot_v11.strip_leading_mentions("  @1   .hp") == ".hp"
    assert onebot_v11.strip_leading_mentions(".hp @1") == ".hp @1"


def test_at_reply_message():
    """at_reply 组装真 @ 消息段 + 文案。"""
    message = onebot_v11.at_reply(22222, "还没有在本群建立角色卡")
    assert message == Message(MessageSegment.at("22222")) + " 还没有在本群建立角色卡"


# =========================================================================
# 带标记取参（commands/base.py）
# =========================================================================


def test_rest_with_mentions_equals_plain_rest():
    """无 @ 时带标记取参与既有 get_command_rest 完全一致。"""
    for text in (".hp 队友A -d4", ".ri+3 地精", ".init del 地精", ".力量检定", ".hp"):
        event = _event(Message(text))
        assert base.get_command_rest_with_mentions(event) == base.get_command_rest(event)


def test_rest_with_mentions_keeps_mark():
    """有 @ 时参数中保留 @<qq> 标记（含紧凑写法 .ri+3@某人）。"""
    event = _event(Message(".hp ") + MessageSegment.at(22222) + " -d4")
    assert base.get_command_rest_with_mentions(event) == " @22222 -d4"
    # 纯文本取参仍是适配器语义（@ 段消失），两者差异是本次功能的立足点
    assert base.get_command_rest(event) == "  -d4"


def test_leading_mention_command_still_matched():
    """@ 在命令之前时命令名照常命中、参数正确。"""
    event = _event(MessageSegment.at(22222) + " .hp -d4")
    assert base.get_command_rest_with_mentions(event) == " -d4"
    parsed = base.parse_command_with_mentions(event)
    assert parsed is not None and parsed[1] == "hp"


def test_leading_bot_mention_command_still_matched():
    """@ 机器人在命令之前时（to_me 习惯）同样命中且不产生 @ 目标。"""
    event = _event(MessageSegment.at(1) + " .ri+3")
    assert base.get_command_rest_with_mentions(event) == "+3"
    assert onebot_v11.list_mentions(event) == []
