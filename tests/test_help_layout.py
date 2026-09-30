"""``.help`` 版式与文案的纪律断言（2026-09-28 用户定稿的排版）。

纪律（用户手改稿定）：

- 组清单每行 ≤ 30 字，整组 ≤ 10 行（含标题与末尾链接行）；
- 详情每行 ≤ 40 字、整条 ≤ 6 行（含末尾链接行）；
- 总览 / 目录 / 链接 / 关于 / 骰主 / 联系各有行数上限；
- 组清单里出现的命令写法必须真实存在（已注册命令，或只进帮助的条目标签），
  避免文案与命令表脱节；
- 每条回复登记的文档页（``doc``）必须真实存在于 ``docs/``，杜绝死链（批次 A）。
"""

from pathlib import Path

import pytest

from nonebot_plugin_dnddicer.commands import base, help_layout
from nonebot_plugin_dnddicer.commands import text as cmd_text
from nonebot_plugin_dnddicer.version import __version__

#: 仓库根（用于校验 ``doc`` 指向的站点页面真实存在）
_REPO_ROOT = Path(__file__).resolve().parents[1]
#: 站点文档目录
_DOCS_DIR = _REPO_ROOT / "docs"

#: 组清单每行字数上限
_GROUP_LINE_LIMIT = 30
#: 组清单总行数上限（含标题与末尾文档站链接行；角色组最长，用户定稿即 11 行）
_GROUP_TOTAL_LIMIT = 11
#: 详情每行字数上限（用法行可以长一些）
_DETAIL_LINE_LIMIT = 40
#: 详情总行数上限（含末尾文档站链接行）
_DETAIL_TOTAL_LIMIT = 6

#: 组清单里不是「命令写法」的行（标题、前置提示、后缀说明）
_NON_COMMAND_PREFIXES = ("【", "⚠️", "后缀支持")


def _detail_texts() -> dict[str, str]:
    """全部命令详情文案（含骰主命令）。"""
    return base.get_registered_commands(include_hidden=True)


def _is_known_command(token: str) -> bool:
    """命令写法是否真实存在（注册命令按前缀匹配，或只进帮助的条目标签）。"""
    name, _ = base.match_command_name(token)
    if name is not None:
        return True
    return any(
        token in (entry.name, *entry.tokens) for entry in help_layout.HELP_ONLY_ENTRIES
    )


def _line_is_known(body: str) -> bool:
    """整行写法是否可解析：``.[属性]检定`` 这类占位写法走只进帮助条目的包含匹配。"""
    if body.startswith(".["):
        return help_layout.find_help_only(body) is not None
    token = body.split(" ")[0].split("[")[0].split("/")[0].strip().lstrip(".")
    return bool(token) and _is_known_command(token)


def _command_token(line: str) -> str:
    """取组清单某行开头的命令写法（去掉说明与参数）。"""
    body = line.split("　")[0].strip()
    token = body.split(" ")[0].split("[")[0].split("/")[0].strip()
    return token.lstrip(".")


def test_group_line_and_total_limits():
    """组清单行数与每行字数上限。"""
    for name, lines, _doc in help_layout.HELP_GROUPS:
        assert len(lines) + 1 <= _GROUP_TOTAL_LIMIT, f"「{name}」组清单过长"
        for line in lines:
            assert len(line) <= _GROUP_LINE_LIMIT, f"「{name}」组清单行过长：{line}"


def test_group_lines_reference_real_commands():
    """组清单里出现的命令写法必须真实存在（避免文案与命令表脱节）。"""
    for name, lines, _doc in help_layout.HELP_GROUPS:
        for line in lines:
            if line.startswith(_NON_COMMAND_PREFIXES):
                continue
            body = line.split("　")[0].strip()
            assert _line_is_known(body), f"「{name}」组清单提到不存在的命令：{line}"


def test_group_lines_use_comment_style():
    """组清单的命令行统一「命令[参数]　#短说明」写法（标题与提示行例外）。"""
    for name, lines, _doc in help_layout.HELP_GROUPS:
        for line in lines:
            if line.startswith(_NON_COMMAND_PREFIXES):
                continue
            assert "　#" in line, f"「{name}」组清单行缺少「　#」说明：{line}"
            usage, comment = line.split("　#", 1)
            assert usage.startswith("."), f"「{name}」组清单行未以 . 开头：{line}"
            assert comment, f"「{name}」组清单行说明为空：{line}"


def test_detail_limits():
    """每条命令详情的行数与每行字数上限（含末尾链接行的余量）。"""
    for name, detail in _detail_texts().items():
        lines = detail.splitlines()
        assert len(lines) + 1 <= _DETAIL_TOTAL_LIMIT + 1, f"「{name}」详情过长"
        for line in lines:
            assert len(line) <= _DETAIL_LINE_LIMIT, f"「{name}」详情行过长：{line}"


def test_detail_first_line_is_usage():
    """详情首行是用法行（以 . 开头）；后续说明行缩进两格。"""
    for name, detail in _detail_texts().items():
        lines = detail.splitlines()
        assert lines[0].startswith("."), f"「{name}」详情首行不是用法：{lines[0]}"
        for line in lines[1:]:
            assert line.startswith("  "), f"「{name}」详情说明行未缩进：{line}"


def test_help_only_entries_have_short_lines():
    """只进帮助的条目：行数与字数同样受限。"""
    for entry in help_layout.HELP_ONLY_ENTRIES:
        lines = entry.text.splitlines()
        assert len(lines) + 1 <= _DETAIL_TOTAL_LIMIT + 1, f"「{entry.name}」条目过长"
        for line in lines:
            assert len(line) <= _DETAIL_LINE_LIMIT, f"「{entry.name}」条目行过长：{line}"


def test_entry_limits():
    """总览 / 目录 / 链接 / 关于 / 骰主 / 联系的行数上限。"""
    landing = cmd_text.TXT_HELP_LANDING.format(version=__version__)
    catalog = cmd_text.TXT_HELP_CATALOG
    link = cmd_text.TXT_HELP_LINK.format(url=cmd_text.TXT_HELP_DOCS_BASE)
    about = cmd_text.TXT_HELP_ABOUT.format(
        version=__version__, repo="https://example.com", group="1"
    )
    assert len(landing.splitlines()) <= 9
    assert len(catalog.splitlines()) <= 9
    assert len(link.splitlines()) <= 6
    assert len(about.splitlines()) <= 8
    assert len(cmd_text.TXT_HELP_MASTER.splitlines()) <= 4
    assert len(cmd_text.TXT_HELP_CONTACT.splitlines()) <= 4


def test_catalog_lists_every_group():
    """目录逐组列全，且关键词与分组表一致。"""
    catalog = cmd_text.TXT_HELP_CATALOG
    for name, _lines, _doc in help_layout.HELP_GROUPS:
        assert f".help {name} " in catalog, f"目录缺少分组「{name}」"


def test_group_synonyms_resolve():
    """组别名必须指向真实存在的分组。"""
    for alias, target in help_layout.GROUP_SYNONYMS:
        group = help_layout.find_group(alias)
        assert group is not None, f"组别名「{alias}」未命中"
        assert group[0] == target, f"组别名「{alias}」指向了「{group[0]}」"


def test_pattern_entries_not_command_names():
    """只进帮助的条目不得同时是注册命令名（否则详情会被命令详情覆盖）。"""
    commands = base.get_registered_commands(include_hidden=True)
    for entry in help_layout.HELP_ONLY_ENTRIES:
        assert entry.name not in commands, f"「{entry.name}」既是帮助条目又是命令名"


@pytest.mark.parametrize("keyword", ["命令", "列表", "指令", "菜单", "list"])
def test_catalog_keywords(keyword: str):
    """目录入口的关键词集合。"""
    assert help_layout.is_catalog_keyword(keyword)


def test_no_emoji_in_replies_except_warning():
    """除分组前置提示的 ⚠️ 外，帮助文案不带表情符号（保持纯文本可读）。"""
    blobs = [cmd_text.TXT_HELP_LANDING, cmd_text.TXT_HELP_CATALOG, cmd_text.TXT_HELP_LINK]
    blobs += [line for _name, lines, _doc in help_layout.HELP_GROUPS for line in lines]
    for blob in blobs:
        assert "⚠️" not in blob or blob.startswith("⚠️")


# ── 文档页深链（批次 A）──────────────────────────────────────────────────


def _registered_docs() -> dict[str, str]:
    """全部登记文档页的条目名 → 站内相对路径（命令 + 分组 + 只进帮助条目）。"""
    docs = {
        name: base.get_command_doc(name)
        for name in base.get_registered_commands(include_hidden=True)
    }
    docs.update({name: doc for name, _lines, doc in help_layout.HELP_GROUPS})
    docs.update({entry.name: entry.doc for entry in help_layout.HELP_ONLY_ENTRIES})
    return docs


def test_registered_docs_exist():
    """每个登记的文档页都必须真实存在（``docs/<path>.md``），杜绝死链。"""
    for name, doc in _registered_docs().items():
        if not doc:
            continue  # 留空 = 无对应页，链接行回落站点首页
        assert doc.startswith("guide/"), f"「{name}」的文档页不在 guide/ 下：{doc}"
        assert (_DOCS_DIR / f"{doc}.md").is_file(), f"「{name}」的文档页不存在：{doc}"


def test_group_docs_registered():
    """7 个分组都要登记文档页（组清单末尾的链接行据此生成深链）。"""
    for name, _lines, doc in help_layout.HELP_GROUPS:
        assert doc, f"分组「{name}」未登记文档页"


def test_help_only_docs_registered():
    """按消息模式触发的条目都要登记文档页（``.master`` 暂无对应页，留空）。"""
    for entry in help_layout.HELP_ONLY_ENTRIES:
        if entry.name == "master":
            continue
        assert entry.doc, f"条目「{entry.name}」未登记文档页"
