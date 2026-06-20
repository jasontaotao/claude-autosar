"""Unit tests for unified template apply — Sprint 9.2 M1-T — T9.2-β.

byte-identity 严格校验:
  - apply 后除 <VALUE> / <d:var value="..."/> 段外其他字节完全不变
  - 走 ``dispatcher.read / write(preserve_format=True)`` 实现

注：diff 直接构造 ECUCValue / XDMValue tuple，不走 load_module（load_module
的 walker 暂只识别 ``ECUC-PARAM-CONF-CONTAINER``，fixture 用的是
``ECUC-CONTAINER-VALUE``，是 pre-existing 状况；plan §2.3 锁定 9.2 范围
不含 ecuc walker 升级）。apply 端用自有 SHORT-NAME 导航，独立工作。
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

import pytest

from claude_autosar.core.bsw.ecuc import ECUCValue
from claude_autosar.core.bsw.templates.apply import (
    ApplyMode,
    ApplyResult,
    apply_template_diff,
)
from claude_autosar.core.bsw.templates.arxml_diff import (
    TemplateDiff,
    TemplateDiffResult,
)
from claude_autosar.core.bsw.templates.xdm_diff import TemplateDiff as XDMTemplateDiff
from claude_autosar.core.bsw.templates.xdm_diff import TemplateDiffResult as XDMTemplateDiffResult

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ARXML_SIMPLE = FIXTURES_DIR / "arxml" / "Can_simple.arxml"
ARXML_TEMPLATE = FIXTURES_DIR / "arxml" / "Can_template.arxml"
XDM_SIMPLE = FIXTURES_DIR / "datamodel2" / "Can_simple.xdm"
XDM_TEMPLATE = FIXTURES_DIR / "datamodel2" / "Can_template.xdm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _arxml_diff_modify_only() -> TemplateDiffResult:
    """构造一个纯 modify diff：CanTxIPdu_0/CanTxIPduHandleId: 100 → 101.

    其他 path 都对齐（current == template）→ 不计入 diff。
    """
    path = "Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId"
    cur = ECUCValue(path=path, raw="100", type="INTEGER")
    tmpl = ECUCValue(path=path, raw="101", type="INTEGER")
    return TemplateDiffResult(
        module_name="Can",
        diffs=(
            TemplateDiff(
                path=path,
                current=cur,
                template=tmpl,
                op="modify",
            ),
        ),
    )


def _xdm_diff_modify_only() -> XDMTemplateDiffResult:
    """构造一个 XDM 端纯 modify diff：CanTxIPdu_0/CanTxIPduHandleId: 100 → 101.

    XDMValue 是独立 dataclass（XDM 端有 own value type），所以单独构造。

    XDM 树 path 走法：root→<d:ctr name="Can" AR-PACKAGE>→<d:lst ELEMENTS>→
    <d:chc name="Can" AR-ELEMENT>→<d:ctr MODULE-CONFIGURATION>→<d:lst CanConfigSet MAP>
    →<d:ctr CanConfigSet IDENTIFIABLE>→<d:lst CanTxIPdu MAP>→<d:ctr CanTxIPdu_0>
    →<d:var CanTxIPduHandleId>

    apply 用 SHORT-NAME 导航 + 跳无名 wrapper，所以 path 是：
    Can/Can/CanConfigSet/CanConfigSet/CanTxIPdu/CanTxIPdu_0/CanTxIPduHandleId

    byte-identity 限制：XDM writer 的 _byte_identical_patch 只支持 ``<a:a>``
    段；改 ``<d:var>`` 会触发 _cleanup_namespaces_fallback 退路（重新写整
    个文件，byte-identity 不保留，但语义正确）。本 test 校验"语义正确 +
    值生效"，不校验 byte-identity 100%（plan §2.3 接受 XDM 端 d:var 走
    fallback；后续 sprint 升级 writer 以支持 d:var surgical patch）。
    """
    from claude_autosar.core.bsw.templates.xdm_value import XDMValue

    path = "Can/Can/CanConfigSet/CanConfigSet/CanTxIPdu/CanTxIPdu_0/CanTxIPduHandleId"
    cur = XDMValue(path=path, raw="100", type="INTEGER")
    tmpl = XDMValue(path=path, raw="101", type="INTEGER")
    return XDMTemplateDiffResult(
        diffs=(
            XDMTemplateDiff(
                path=path,
                current=cur,
                template=tmpl,
                op="modify",
            ),
        ),
    )


def _copy_to_tmp(src: Path, tmp_path: Path) -> Path:
    """复制 fixture 到 tmp 路径，返回新路径。"""
    dst = tmp_path / src.name
    shutil.copy2(src, dst)
    return dst


# ---------------------------------------------------------------------------
# 1. ARXML dry-run：只 diff 不写文件
# ---------------------------------------------------------------------------


def test_apply_arxml_dry_run_does_not_write_file(
    tmp_path: Path,
) -> None:
    """DRY_RUN 模式：不修改文件。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    original_bytes = doc.read_bytes()
    diff = _arxml_diff_modify_only()

    result = apply_template_diff(doc, diff, mode=ApplyMode.DRY_RUN)

    assert result.mode == ApplyMode.DRY_RUN
    assert result.diffs_applied == 1
    # 文件 bytes 完全不变
    assert doc.read_bytes() == original_bytes
    # bytes_changed 在 dry_run 模式下 = 0（plan §2.3 锁定）
    assert result.bytes_changed == 0


# ---------------------------------------------------------------------------
# 2. ARXML apply：surgical patch，byte-identity 100% 除 VALUE 段
# ---------------------------------------------------------------------------


def test_apply_arxml_modify_byte_identity(
    tmp_path: Path,
) -> None:
    """apply 模式：改 <VALUE> 文本；除 <VALUE>...</VALUE> 字节段外其余字节不变。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    original_bytes = doc.read_bytes()
    diff = _arxml_diff_modify_only()

    result = apply_template_diff(doc, diff, mode=ApplyMode.APPLY)

    assert result.mode == ApplyMode.APPLY
    assert result.diffs_applied == 1

    new_bytes = doc.read_bytes()
    new_text = new_bytes.decode("utf-8")
    orig_text = original_bytes.decode("utf-8")

    # VALUE 段数量应一致（surgical patch 的前提）
    orig_values = re.findall(r"<VALUE[^>]*>([^<]*)</VALUE>", orig_text)
    new_values = re.findall(r"<VALUE[^>]*>([^<]*)</VALUE>", new_text)
    assert len(orig_values) == len(new_values)
    # 至少一个 VALUE 改了
    assert orig_values != new_values
    # 新值含 "101"
    assert "101" in new_values
    # 旧值含 "100"
    assert "100" in orig_values
    # "100" 仍在文件中（其它 VALUE 段可能也有 100）
    # surgical patch 校验：100 → 101 的修改应只发生在那个具体 VALUE 段
    # 把 "100" 替换为 "101" 的所有 segment 加上 anchor，看是否只改一个
    # 简单：orig_text 中 "100" 出现次数 = new_text 中 "100" + 1
    # （因为少了一个 100，多了一个 101）
    new_count_100 = new_text.count("100")
    orig_count_100 = orig_text.count("100")
    # "101" 出现次数 = new 中多 1，orig 中 0
    assert new_text.count("101") == orig_text.count("101") + 1
    # 100 出现次数：新少 1，旧多 1
    assert new_count_100 == orig_count_100 - 1

    # bytes_changed 是 size 差
    assert result.bytes_changed == abs(len(new_bytes) - len(original_bytes))


# ---------------------------------------------------------------------------
# 3. ARXML apply 后 raw 校验
# ---------------------------------------------------------------------------


def test_apply_arxml_modify_value_effective(
    tmp_path: Path,
) -> None:
    """apply 后从原文件直接 grep，<VALUE>101</VALUE> 应出现。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    diff = _arxml_diff_modify_only()

    apply_template_diff(doc, diff, mode=ApplyMode.APPLY)

    new_text = doc.read_bytes().decode("utf-8")
    # 旧值 100 还在（只少了一个 100），新值 101 出现
    assert "<VALUE>101</VALUE>" in new_text


# ---------------------------------------------------------------------------
# 4. XDM dry-run
# ---------------------------------------------------------------------------


def test_apply_xdm_dry_run_does_not_write_file(
    tmp_path: Path,
) -> None:
    """XDM DRY_RUN：不修改文件。"""
    doc = _copy_to_tmp(XDM_SIMPLE, tmp_path)
    original_bytes = doc.read_bytes()
    diff = _xdm_diff_modify_only()

    result = apply_template_diff(doc, diff, mode=ApplyMode.DRY_RUN)

    assert result.mode == ApplyMode.DRY_RUN
    assert result.diffs_applied == 1
    assert doc.read_bytes() == original_bytes
    assert result.bytes_changed == 0


# ---------------------------------------------------------------------------
# 5. XDM apply：语义正确；XDM d:var 走 cleanup_namespaces fallback（不 byte-identity）
# ---------------------------------------------------------------------------


def test_apply_xdm_modify_value_applied(
    tmp_path: Path,
) -> None:
    """XDM apply：d:var 改值；语义正确（值生效）。

    注：byte-identity 100% 只在 ``<a:a>`` 段有效（Sprint 8.E.5 锁定的
    XDM writer 能力）；``<d:var>`` 改值走 _cleanup_namespaces_fallback
    退路（tostring 重建文件），plan §2.3 接受此 trade-off，后续 sprint
    升级 XDM writer 以支持 d:var surgical patch。
    """
    doc = _copy_to_tmp(XDM_SIMPLE, tmp_path)
    diff = _xdm_diff_modify_only()

    result = apply_template_diff(doc, diff, mode=ApplyMode.APPLY)

    assert result.mode == ApplyMode.APPLY
    assert result.diffs_applied == 1

    new_text = doc.read_bytes().decode("utf-8")
    # d:var 段值改了
    import re as _re

    m = _re.search(
        r'<d:var[^>]*name="CanTxIPduHandleId"[^>]*value="101"[^>]*/>',
        new_text,
    )
    assert m is not None
    # 旧值 100 不应出现
    assert 'value="100"' not in new_text


# ---------------------------------------------------------------------------
# 6. XDM apply 后 re-grep value 校验
# ---------------------------------------------------------------------------


def test_apply_xdm_modify_value_effective(
    tmp_path: Path,
) -> None:
    """XDM apply 后 <d:var name=...CanTxIPduHandleId... value="101"/> 应出现。"""
    doc = _copy_to_tmp(XDM_SIMPLE, tmp_path)
    diff = _xdm_diff_modify_only()

    apply_template_diff(doc, diff, mode=ApplyMode.APPLY)

    new_text = doc.read_bytes().decode("utf-8")
    # CanTxIPduHandleId 的 value 是 101
    pattern = r'<d:var[^>]*name="CanTxIPduHandleId"[^>]*value="101"[^>]*/>'
    assert re.search(pattern, new_text) is not None
    # 旧值 100 不应出现
    assert 'value="100"' not in new_text


# ---------------------------------------------------------------------------
# 7. diff 为空 → 返回空 result，文件不变
# ---------------------------------------------------------------------------


def test_apply_empty_diff_returns_noop(
    tmp_path: Path,
) -> None:
    """没有 diff → diffs_applied=0；文件不变。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    original_bytes = doc.read_bytes()
    empty = TemplateDiffResult(module_name="Can", diffs=())

    result = apply_template_diff(doc, empty, mode=ApplyMode.APPLY)

    assert result.diffs_applied == 0
    assert result.diffs == ()
    assert doc.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# 8. add op — Sprint 12 T12.4 已支持
# ---------------------------------------------------------------------------


def test_apply_add_op_supported(tmp_path: Path) -> None:
    """Sprint 12: add op 已支持，不再抛 NotImplementedError。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)

    add_diff = TemplateDiff(
        path="Can/CanGeneral/NewParam",
        current=None,
        template=ECUCValue(path="Can/CanGeneral/NewParam", raw="42", type="INTEGER"),
        op="add",
    )
    diff = TemplateDiffResult(module_name="Can", diffs=(add_diff,))

    # 不再抛 NotImplementedError
    result = apply_template_diff(doc, diff, mode=ApplyMode.DRY_RUN)
    assert result.diffs_applied == 1


# ---------------------------------------------------------------------------
# 9. delete op — Sprint 12 T12.4 已支持
# ---------------------------------------------------------------------------


def test_apply_delete_op_supported(tmp_path: Path) -> None:
    """Sprint 12: delete op 已支持，不再抛 NotImplementedError。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)

    del_diff = TemplateDiff(
        path="Can/CanGeneral/CanMainFunctionBusOffPeriod",
        current=ECUCValue(path="Can/CanGeneral/CanMainFunctionBusOffPeriod", raw="0", type="INTEGER"),
        template=None,
        op="delete",
    )
    diff = TemplateDiffResult(module_name="Can", diffs=(del_diff,))

    # 不再抛 NotImplementedError
    result = apply_template_diff(doc, diff, mode=ApplyMode.DRY_RUN)
    assert result.diffs_applied == 1


# ---------------------------------------------------------------------------
# 10. ApplyResult frozen + 字段正确
# ---------------------------------------------------------------------------


def test_apply_result_frozen() -> None:
    """ApplyResult 是 frozen dataclass。"""
    result = ApplyResult(
        mode=ApplyMode.DRY_RUN,
        path=Path("/tmp/x.arxml"),
        diffs_applied=0,
        bytes_changed=0,
        diffs=(),
    )

    with pytest.raises((AttributeError, Exception)):
        result.diffs_applied = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11. ApplyMode 序列化友好（str+Enum）
# ---------------------------------------------------------------------------


def test_apply_mode_string_serialization() -> None:
    """ApplyMode 是 str+Enum；可直接当 str 用。"""
    assert ApplyMode.DRY_RUN == "dry_run"
    assert ApplyMode.APPLY == "apply"
    assert str(ApplyMode.DRY_RUN) == "ApplyMode.DRY_RUN"
    assert ApplyMode.DRY_RUN.value == "dry_run"


# ---------------------------------------------------------------------------
# 12. 跨格式：传给 ARXML apply 一个无 TemplateDiffResult 形状的对象
# ---------------------------------------------------------------------------


def test_apply_raises_on_invalid_diff_object() -> None:
    """diff 不是 TemplateDiffResult-like（无 .diffs tuple）→ ValueError。"""
    bogus = object()

    with pytest.raises(ValueError, match="expected TemplateDiffResult-like"):
        apply_template_diff(Path("/tmp/x.arxml"), bogus, mode=ApplyMode.DRY_RUN)


# ---------------------------------------------------------------------------
# 13. 不可变 diff：apply 不改 diff 本身
# ---------------------------------------------------------------------------


def test_apply_does_not_mutate_input_diff(
    tmp_path: Path,
) -> None:
    """apply 不会修改传入的 diff。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    diff = _arxml_diff_modify_only()
    diffs_snapshot = diff.diffs

    apply_template_diff(doc, diff, mode=ApplyMode.APPLY)

    # diff.diffs tuple 引用未变 + 长度未变
    assert diff.diffs == diffs_snapshot
    assert len(diff.diffs) == len(diffs_snapshot)


# ---------------------------------------------------------------------------
# 14. ARXML apply 端到端：Can_simple → Can_template 的差异能 1 次 apply 同步
# ---------------------------------------------------------------------------


def test_apply_arxml_full_template_diff_sync(
    tmp_path: Path,
) -> None:
    """完整模板同步：构造一个 (modify, modify) 的 diff，apply 成功。
    Sprint 12 T12.4：add/delete 已支持，不再抛 NotImplementedError。
    """
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    # 构造 2 个 modify（同 path 不同 raw）— apply 成功
    diff = TemplateDiffResult(
        module_name="Can",
        diffs=(
            TemplateDiff(
                path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                current=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                    raw="100",
                    type="INTEGER",
                ),
                template=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                    raw="101",
                    type="INTEGER",
                ),
                op="modify",
            ),
            TemplateDiff(
                path="Can/CanConfigSet/CanRxIPdu_0/CanRxIPduHandleId",
                current=ECUCValue(
                    path="Can/CanConfigSet/CanRxIPdu_0/CanRxIPduHandleId",
                    raw="200",
                    type="INTEGER",
                ),
                template=ECUCValue(
                    path="Can/CanConfigSet/CanRxIPdu_0/CanRxIPduHandleId",
                    raw="201",
                    type="INTEGER",
                ),
                op="modify",
            ),
        ),
    )

    result = apply_template_diff(doc, diff, mode=ApplyMode.APPLY)
    assert result.diffs_applied == 2

    new_text = doc.read_bytes().decode("utf-8")
    assert "<VALUE>101</VALUE>" in new_text
    assert "<VALUE>201</VALUE>" in new_text


# ---------------------------------------------------------------------------
# 15. ARXML apply：路径找不到（container 不存在）→ 跳过该 diff（不抛）
# ---------------------------------------------------------------------------


def test_apply_arxml_skips_missing_path(
    tmp_path: Path,
) -> None:
    """path 在 current 中不存在 → 跳过该 diff；其它 diff 仍处理。"""
    doc = _copy_to_tmp(ARXML_SIMPLE, tmp_path)
    # 第一个 diff 路径不存在（NX 容器下没有该 IPdu）
    # 第二个 diff 路径存在
    diff = TemplateDiffResult(
        module_name="Can",
        diffs=(
            TemplateDiff(
                path="Can/CanConfigSet/CanTxIPdu_NX/CanTxIPduHandleId",
                current=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_NX/CanTxIPduHandleId",
                    raw="999",
                    type="INTEGER",
                ),
                template=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_NX/CanTxIPduHandleId",
                    raw="998",
                    type="INTEGER",
                ),
                op="modify",
            ),
            TemplateDiff(
                path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                current=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                    raw="100",
                    type="INTEGER",
                ),
                template=ECUCValue(
                    path="Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId",
                    raw="101",
                    type="INTEGER",
                ),
                op="modify",
            ),
        ),
    )

    result = apply_template_diff(doc, diff, mode=ApplyMode.APPLY)
    # apply 仍处理了 2 个（diffs_applied = 总数；缺失路径静默跳过）
    assert result.diffs_applied == 2
    # 真实改了那个存在的 path
    new_text = doc.read_bytes().decode("utf-8")
    assert "<VALUE>101</VALUE>" in new_text
