"""查询范围书目表单测（query/books.py，离线纯数据）。

覆盖：键查找（大小写不敏感）、整目录提示（合作内容 / 寄居目录）、展示分组、
「全部」保留字、目录名反查，以及表格自身的一致性（键与目录不重复、分组有效）。
"""

from __future__ import annotations

from nonebot_plugin_dnddicer.query import books


# ── 表格一致性 ──────────────────────────────────────────────────────────


def test_table_integrity():
    """键与目录名都不重复；分组名有效；键与目录非空。"""
    keys = [entry.key for entry in books.SCOPE_ENTRIES]
    categories = [entry.category for entry in books.SCOPE_ENTRIES]
    assert len(keys) == len(set(keys))
    assert len(categories) == len(set(categories))
    valid_sections = {section for section, _ in books.SECTION_TITLES}
    for entry in books.SCOPE_ENTRIES:
        assert entry.key and entry.category and entry.title
        assert entry.section in valid_sections


def test_table_covers_core_books():
    """核心三本与几个常用扩展在表内（抽样锁定，防误删）。"""
    for key, category in (
        ("PHB24", "玩家手册2024"),
        ("DMG24", "城主指南2024"),
        ("MM25", "怪物图鉴2025"),
        ("XGE", "珊娜萨的万事指南"),
        ("TCE", "塔莎的万事坩埚"),
        ("PHB14", "玩家手册"),
        ("MPMM", "多元宇宙的怪物"),
        ("3PP", "第三方"),
        ("ADV", "模组"),
        ("FR", "被遗忘的国度"),
        ("MISC", "其他"),
    ):
        entry = books.find_entry(key)
        assert entry is not None and entry.category == category


# ── 查找与提示 ──────────────────────────────────────────────────────────


def test_find_entry_case_insensitive():
    """键查找大小写不敏感；未知键返回 None。"""
    assert books.find_entry("phb24") is books.find_entry("PHB24")
    assert books.find_entry(" Phb24 ") is not None
    assert books.find_entry("不存在") is None
    assert books.find_entry("") is None


def test_find_entry_rejects_chinese_book_name():
    """设置只接受缩写：中文书名不解析。"""
    assert books.find_entry("玩家手册2024") is None
    assert books.find_entry("第三方") is None


def test_umbrella_hint_partner_books():
    """合作内容的书目缩写 → 提示改用 3PP。"""
    for key in ("Dk", "GH", "TCSR", "VTMBB", "FGFD"):
        entry = books.umbrella_hint(key)
        assert entry is not None and entry.key == "3PP"


def test_umbrella_hint_fr_and_hosts():
    """被遗忘的国度 → FR；寄居目录的作品 → 宿主书（JRC→ADV、SAiS→AAG、PAitM→SO）。"""
    assert books.umbrella_hint("FRHoF").key == "FR"
    assert books.umbrella_hint("LFL").key == "FR"
    assert books.umbrella_hint("JRC").key == "ADV"
    assert books.umbrella_hint("SAiS").key == "AAG"
    assert books.umbrella_hint("PAitM").key == "SO"


def test_umbrella_hint_unknown_and_known_none():
    """可设置项与完全未知的键都不给提示（提示只服务「该怎么改」）。"""
    assert books.umbrella_hint("PHB24") is None
    assert books.umbrella_hint("不存在") is None


# ── 展示 ────────────────────────────────────────────────────────────────


def test_sections_for_display_groups():
    """分组展示：每组非空、条目数合计等于表内总数、整目录组在最后。"""
    sections = books.sections_for_display()
    total = sum(len(entries) for _, entries in sections)
    assert total == len(books.SCOPE_ENTRIES)
    titles = [title for title, _ in sections]
    assert titles[-1].startswith("整目录")
    assert all(entries for _, entries in sections)


def test_category_display():
    """目录名展示为「键 中文名」；非可设置目录原样返回。"""
    assert books.category_display("玩家手册2024") == "PHB24 玩家手册2024"
    assert books.category_display("第三方") == "3PP 第三方（合作内容）"
    assert books.category_display("未分类") == "未分类"


def test_entry_by_category():
    """目录名反查条目。"""
    assert books.entry_by_category("模组").key == "ADV"
    assert books.entry_by_category("不存在") is None


def test_is_all_word():
    """「全部」保留字（含 all，大小写不敏感）。"""
    assert books.is_all_word("全部")
    assert books.is_all_word("all")
    assert books.is_all_word("ALL")
    assert not books.is_all_word("PHB24")
    assert not books.is_all_word("")
