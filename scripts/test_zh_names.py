"""Display names are Traditional Chinese; Japanese is kept only as a fallback."""

from __future__ import annotations

from zh_names import display_name_zh, stamp_display_name


def test_greninja_sar_keeps_set_code() -> None:
    name, status = display_name_zh(
        "ゲッコウガex SAR [M6a 125/103](拡張パック「30th CELEBRATION」)"
    )
    assert status == "zh"
    assert name.startswith("甲賀忍蛙ex SAR")
    assert "M6a 125/103" in name
    assert "ゲッコウガ" not in name


def test_lillie_uses_official_title() -> None:
    name, status = display_name_zh(
        "リーリエの決心 SR [M1L 086/063](拡張パック「メガブレイブ」)"
    )
    assert status == "zh"
    assert name.startswith("莉莉艾的決意 SR")
    assert "M1L 086/063" in name
    assert "超級勇氣" in name


def test_may_encouragement_and_obsidian_box() -> None:
    may, may_status = display_name_zh(
        "メイのはげまし SAR [M3 115/080](拡張パック「ムニキスゼロ」)"
    )
    assert may_status == "zh"
    assert may.startswith("鳴依的勉勵 SAR")
    assert "虛無歸零" in may

    box, box_status = display_name_zh("黒炎の支配者 BOX 未開封")
    assert box_status == "zh"
    assert box == "黯焰支配者 BOX（未開封）"


def test_unknown_kana_falls_back_to_japanese() -> None:
    raw = "わけのわからないカード SAR"
    name, status = display_name_zh(raw)
    assert status == "fallback"
    assert name == raw


def test_keeps_existing_chinese_when_translation_fails() -> None:
    row = {
        "name_zh": "星晶奇跡 BOX（未開封）",
        "name_jp": "わけのわからない BOX 未開封",
        "search_jp": "わけのわからない BOX 未開封",
    }
    stamp_display_name(row)
    assert row["name_zh"] == "星晶奇跡 BOX（未開封）"
    assert "name_zh_fallback" not in row
    assert row["search_jp"].startswith("わけのわからない")


def test_stellar_miracle_box() -> None:
    name, status = display_name_zh("ステラミラクル BOX 未開封")
    assert status == "zh"
    assert name == "星星奇跡 BOX（未開封）"


def test_already_chinese_is_unchanged() -> None:
    raw = "梵高比卡超 PSA10"
    name, status = display_name_zh(raw)
    assert status == "zh"
    assert name == raw
