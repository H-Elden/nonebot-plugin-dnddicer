"""牌堆与随机表：Dice! JSON 兼容、抽取、图片与随机源。

模块划分：
- ``parser``   Dice! JSON 解析与限制
- ``library``  自定义牌堆加载、搜索与重载
- ``draw``     放回/不放回、嵌套、表达式、图片标记
- ``media``    图片路径安全、魔数/体积校验与读取
- ``runtime``  默认随机 / 固定序列（测试与取证）
"""

from __future__ import annotations

from .draw import MAX_TIMES, DrawContext, draw
from .errors import (
    DeckAmbiguous,
    DeckCountOutOfRange,
    DeckEmpty,
    DeckError,
    DeckIndexOutOfRange,
    DeckNotFound,
)
from .library import DeckLibrary, DeckResolution
from .media import (
    DeckImageError,
    ImageData,
    MAX_IMAGES_PER_DRAW,
    MAX_IMAGES_PER_ENTRY,
    MAX_IMAGE_BYTES,
    MAX_TOTAL_IMAGE_BYTES,
    image_paths,
    load_image,
)
from .models import (
    Deck,
    DeckFileError,
    DeckImagePart,
    DeckItem,
    DeckMeta,
    DeckTextPart,
    DrawResult,
    RenderedEntry,
    normalize_name,
)
from .runtime import (
    DeckRuntime,
    RandomDeckRuntime,
    SequenceDeckRuntime,
    get_runtime,
    reset_runtime,
    set_runtime,
)

__all__ = [
    "Deck",
    "DeckAmbiguous",
    "DeckCountOutOfRange",
    "DeckEmpty",
    "DeckError",
    "DeckFileError",
    "DeckImageError",
    "DeckImagePart",
    "DeckIndexOutOfRange",
    "DeckItem",
    "DeckLibrary",
    "DeckMeta",
    "DeckNotFound",
    "DeckResolution",
    "DeckRuntime",
    "DeckTextPart",
    "DrawContext",
    "DrawResult",
    "ImageData",
    "MAX_IMAGES_PER_DRAW",
    "MAX_IMAGES_PER_ENTRY",
    "MAX_IMAGE_BYTES",
    "MAX_TIMES",
    "MAX_TOTAL_IMAGE_BYTES",
    "RandomDeckRuntime",
    "RenderedEntry",
    "SequenceDeckRuntime",
    "draw",
    "get_runtime",
    "image_paths",
    "load_image",
    "normalize_name",
    "reset_runtime",
    "set_runtime",
]
