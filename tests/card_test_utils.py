"""测试用卡库辅助：直接创建并绑定一张卡。"""

from __future__ import annotations

from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.data import characters


async def create_bound_card(
    group_id: int | str,
    user_id: int | str,
    character: DNDCharacter,
    card_name: str = "测试卡",
) -> str:
    """创建一张卡并绑定到 group_id，返回 card_id。"""
    card_id = await characters.create_card(
        str(user_id), card_name, str(group_id), character
    )
    await characters.bind_card(group_id, user_id, card_id)
    return card_id
