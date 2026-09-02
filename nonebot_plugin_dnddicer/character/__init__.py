"""DND5e 角色卡/检定业务包（自研，语义对齐 nonebot-dicepp character/dnd5e）。

- ``constants``：六属性/18 技能/豁免/攻击词汇表与统一检定条目索引；
- ``models``：AbilityInfo / HPInfo / DNDCharacter（每人在每群一张卡）；
- ``services``：模板解析（CharacterService.parse）、属性初始化与检定
  （AbilityService.initialize / perform_check）。
"""

from .models import AbilityInfo, DNDCharacter, HPInfo  # noqa: F401
from .services import (  # noqa: F401
    AbilityService,
    CharacterService,
    gen_template_char,
    parse_template_to_dict,
)

__all__ = [
    "AbilityInfo",
    "HPInfo",
    "DNDCharacter",
    "AbilityService",
    "CharacterService",
    "gen_template_char",
    "parse_template_to_dict",
]
