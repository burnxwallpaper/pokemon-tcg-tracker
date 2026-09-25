"""Longest-match checks for the HK/TW name map."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from name_zh_map import load_map, rarity_label, translate  # noqa: E402


def test_species_use_official_traditional_chinese() -> None:
    assert translate("ピカチュウ") == "皮卡丘"
    assert translate("リザードン") == "噴火龍"
    assert translate("ゲッコウガ") == "甲賀忍蛙"
    assert translate("イーブイ") == "伊布"
    assert translate("ブラッキー") == "月亮伊布"
    assert translate("ミュウ") == "夢幻"
    assert translate("ミュウツー") == "超夢"
    assert translate("メガニウム") == "大竺葵"


def test_longest_key_beats_mega_prefix_and_mew() -> None:
    assert translate("メガリザードンX") == "超級噴火龍X"
    assert translate("メガニウム") == "大竺葵"
    assert translate("ミュウツー") == "超夢"


def test_regional_prefix_plus_species() -> None:
    assert translate("アローラロコン") == "阿羅拉六尾"
    assert translate("ガラルニャース") == "伽勒爾喵喵"


def test_official_set_and_product_tokens() -> None:
    assert translate("ステラミラクル BOX") == "星晶奇跡 BOX"
    assert translate("拡張パック「黒炎の支配者」") == "擴充包「黯焰支配者」"
    assert translate("ハイクラスパック「テラスタルフェスex」") == "高級擴充包「太晶慶典ex」"
    assert translate("強化拡張パック「ポケモンカード151」") == "強化擴充包「寶可夢卡牌151」"
    assert translate("シャイニートレジャーex") == "閃色寶藏ex"
    assert translate("ソード＆シールド") == "劍&盾"
    assert translate("プレミアムデッキセット") == "頂級牌組組合"
    assert translate("25th アニバーサリー コレクション") == "25週年收藏款"
    assert translate("マスボピカチュウ") == "大師球皮卡丘"


def test_trainer_phrase_and_possessive() -> None:
    assert translate("リーリエの決心 SR") == "莉莉艾的決意 SR"
    assert translate("ナンジャモのハラバリーex") == "奇樹的電肚蛙ex"
    assert translate("ロケット団のミュウツーex") == "火箭隊的超夢ex"


def test_rarity_codes_stay_in_titles() -> None:
    assert translate("ゲッコウガex SAR") == "甲賀忍蛙ex SAR"
    assert translate("SR") == "SR"
    assert rarity_label("SAR") == "特別插畫稀有"
    assert rarity_label("C") == "普通"
    assert translate("ピカチュウ C: マスターボールミラー") == "皮卡丘 C: 大師球反光"


def test_promos_and_xy_mega_prefix() -> None:
    assert translate("ゴッホピカチュウ") == "梵高皮卡丘"
    assert translate("名探偵ピカチュウ") == "名偵探皮卡丘"
    assert translate("MレックウザEX") == "超級烈空坐EX"
    assert "MEGA" in translate("ポケモンカードゲームMEGA")


def test_unknown_kana_is_left_in_place() -> None:
    assert translate("わけのわからない") == "わけのわからない"
    assert translate("ポケキュンコレクション") == "ポケキュンコレクション"


def test_map_groups_are_nonempty() -> None:
    data = load_map()
    counts = data["counts"]
    assert isinstance(counts, dict)
    assert counts["species"] >= 1000
    assert counts["sets"] >= 50
    assert "皮卡丘" in translate("ピカチュウex SAR [M6a 126/103](拡張パック「30th CELEBRATION」)")
