"""Offline checks for Yahoo JP sold-title matching."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.jp_match import (  # noqa: E402
    auction_url,
    build_queries,
    debug_from_comps,
    filter_comps,
    is_fuzzy_closedsearch,
    quote_comps,
    title_matches,
)


def _card(**extra: str) -> dict:
    base = {
        "kind": "psa10",
        "name_jp": "リザードンex SAR シャイニートレジャー PSA10",
        "search_jp": "リザードンex SAR PSA10 シャイニートレジャー",
        "set": "SV4a / 349",
    }
    base.update(extra)
    return base


def test_shiny_charizard_rejects_other_sets_and_lots() -> None:
    item = _card()
    assert title_matches("PSA10 リザードンex SAR 349/190 シャイニートレジャーex", item)
    assert not title_matches("リザードンex SAR PSA10 黒炎の支配者", item)
    assert not title_matches("メガリザードンXex SAR PSA10 シャイニートレジャー", item)
    assert not title_matches(
        "全18枚コンプリート シャイニートレジャーex リザードンex SAR PSA10",
        item,
    )
    assert not title_matches("リザードンex PSA9 シャイニートレジャー", item)
    assert not title_matches("リザードンex SAR シャイニートレジャー PSA10狙い", item)


def test_koraidon_shiny_does_not_use_scarlet() -> None:
    item = _card(
        name_jp="コライドンex UR シャイニートレジャー PSA10",
        search_jp="コライドンex UR PSA10 シャイニートレジャー",
        set="SV4a / 360/190",
    )
    assert title_matches("コライドンex UR PSA10 シャイニートレジャー 360/190", item)
    assert not title_matches("コライドンex SAR PSA10 シャイニートレジャー", item)
    assert not title_matches("コライドンex UR PSA10 シャイニートレジャー", item)
    assert not title_matches("【PSA10】コライドンex SAR SV1S スカーレットex 103/078", item)
    assert not title_matches("PSA10 ミライドンex&コライドンex SAR連番", item)


def test_card_number_and_mega() -> None:
    pika = _card(
        name_jp="ピカチュウ AR PSA10",
        search_jp="ピカチュウ AR PSA10 173/165",
        set="sv2a / 173/165",
    )
    assert title_matches("PSA10 ピカチュウ AR ポケモンカード151 173/165", pika)
    assert not title_matches("ピカチュウex SAR PSA10 198/165", pika)
    assert not title_matches("PSA10 ピカチュウ AR 205/172 VSTARユニバース", pika)
    assert not title_matches("【最安値・極美品・PSA10相当】ピカチュウ AR 173/165", pika)
    assert not title_matches("ピカチュウex SAR PSA10 132/106 超電ブレイカー", pika)
    gengar = _card(
        name_jp="ゲンガーex SR PSA10",
        search_jp="ゲンガーex SR PSA10",
        set="SV5K / 088/071",
    )
    assert title_matches("ゲンガーex SR PSA10 088/071 ワイルドフォース", gengar)
    assert not title_matches("ゲンガーex SAR PSA10 099/071", gengar)
    assert not title_matches("メガゲンガーex SAR PSA10 240/193", gengar)
    mega = _card(
        name_jp="メガゲンガーex SAR PSA10",
        search_jp="メガゲンガーex SAR PSA10",
        set="M2a / 240/193",
    )
    assert title_matches("メガゲンガーex SAR PSA10 240/193", mega)
    assert not title_matches("メガゲンガーex UR PSA10 230/193", mega)
    assert not title_matches("ゲンガーex SR PSA10 088/071", mega)
    iono = _card(
        name_jp="ナンジャモ SAR クレイバースト PSA10",
        search_jp="ナンジャモ SAR PSA10 クレイバースト",
        set="SV2D / 096",
    )
    assert title_matches("ナンジャモ SAR PSA10 クレイバースト", iono)
    assert not title_matches("ナンジャモ SAR PSA10 シャイニートレジャー 350/190", iono)
    assert not title_matches("ナンジャモ SAR PSA10", iono)
    miraidon = _card(
        name_jp="ミライドンex SAR PSA10",
        search_jp="ミライドンex SAR PSA10",
        set="SV1V / 102/078",
    )
    assert title_matches("ミライドンex SAR PSA10 SV1V 102/078", miraidon)
    assert not title_matches("ミライドンex SAR PSA10 102/079", miraidon)


def test_sealed_single_box_only() -> None:
    abyss = {
        "kind": "sealed",
        "name_jp": "アビスアイ BOX 未開封",
        "search_jp": "アビスアイ BOX 未開封",
        "set": "M5",
    }
    assert title_matches(
        "新品未開封シュリンク付きボックス ポケモンカードゲーム 拡張パック「アビスアイ」",
        abyss,
    )
    assert not title_matches("アビスアイ BOX シュリンク付き 未開封 2", abyss)
    assert not title_matches("アビスアイ 1BOX分 30パック 新品未開封", abyss)
    assert not title_matches("アビスアイ4BOX 新品未開封", abyss)
    assert not title_matches("ストームエメラルダ アビスアイ 各1BOX 未開封", abyss)
    box151 = {
        "kind": "sealed",
        "name_jp": "ポケモンカード151 BOX 未開封",
        "search_jp": "ポケモンカード151 BOX 未開封 シュリンク",
        "set": "SV2a",
    }
    assert title_matches("未開封 ポケモンカード151 BOX", box151)
    assert not title_matches("ポケモンカード151 英語版 Booster Bundle 未開封 6BOX", box151)
    assert not title_matches("ポケモンカード151 ボックス開封済み", box151)
    assert not title_matches("未開封BOX テラスタルフェスex 151 セット", box151)
    flame = {
        "kind": "sealed",
        "name_jp": "黒炎の支配者 BOX 未開封",
        "search_jp": "黒炎の支配者 BOX 未開封",
        "set": "SV3",
    }
    assert title_matches("未開封 シュリンク付 黒炎の支配者 1BOX 拡張パック", flame)
    assert not title_matches("デッキビルドBOX 黒炎の支配者 未開封 シュリンク付", flame)
    assert not title_matches("黒炎の支配者 トリプレットビート BOX 未開封 計2点", flame)
    n_card = _card(name_jp="N SAR PSA10", search_jp="N SAR PSA10 ポケモン", set="sv6a")
    assert not title_matches("Nのゾロアークex SAR PSA10 ポケモンカード", n_card)


def test_queries_and_fuzzy_guard() -> None:
    queries = build_queries(_card())
    assert any("シャイニートレジャー" in q and "-メガ" in q for q in queries)
    gengar = build_queries(
        _card(name_jp="ゲンガーex SR PSA10", search_jp="ゲンガーex SR PSA10", set="SV5K / 088/071")
    )
    assert gengar[0].startswith("ゲンガーex SR PSA10")
    assert "088/071" in gengar[0]
    assert "-メガ" in gengar[0]
    assert "WAND" not in gengar[0]
    mega = build_queries(
        _card(name_jp="メガゲンガーex SAR PSA10", search_jp="メガゲンガーex SAR PSA10", set="M2a")
    )
    assert "-メガ" not in mega[0]
    assert is_fuzzy_closedsearch(48, "") is False
    assert is_fuzzy_closedsearch(267, "") is False
    assert is_fuzzy_closedsearch(42000, "コライドンex WAND(100) PSA10") is True
    assert is_fuzzy_closedsearch(8000, "") is True


def test_median_drops_outliers_and_empty_stays_empty() -> None:
    item = _card()
    comps = [
        {"title": "PSA10 リザードンex SAR 349/190 シャイニートレジャーex", "price_jpy": 55000, "bid_count": 3, "auction_id": "a1", "end_time": "2026-09-20T12:00:00+09:00"},
        {"title": "PSA10 リザードンex SAR 349/190 シャイニートレジャーex", "price_jpy": 58000, "bid_count": 1, "auction_id": "a2", "end_time": "2026-09-21T12:00:00+09:00"},
        {"title": "PSA10 リザードンex SAR シャイニートレジャーex", "price_jpy": 57000, "bid_count": 2, "auction_id": "a3", "end_time": "2026-09-22T12:00:00+09:00"},
        {"title": "PSA10 リザードンex SAR 349/190 シャイニートレジャーex", "price_jpy": 59000, "bid_count": 1, "auction_id": "a4", "end_time": "2026-09-23T12:00:00+09:00"},
        {"title": "全18枚コンプリート リザードンex SAR PSA10 シャイニートレジャー", "price_jpy": 90001, "bid_count": 1, "auction_id": "lot", "end_time": "2026-09-23T12:00:00+09:00"},
        {"title": "リザードンex SAR PSA10 黒炎の支配者", "price_jpy": 120000, "bid_count": 1, "auction_id": "other", "end_time": "2026-09-23T12:00:00+09:00"},
        {"title": "PSA10 リザードンex SAR 349/190 シャイニートレジャーex", "price_jpy": 250000, "bid_count": 1, "auction_id": "spike", "end_time": "2026-09-19T12:00:00+09:00"},
    ]
    matched = filter_comps(comps, item)
    assert "lot" not in {c["auction_id"] for c in matched}
    assert "other" not in {c["auction_id"] for c in matched}
    mid, used = quote_comps(matched)
    assert mid == 57500
    assert all(c["auction_id"] != "spike" for c in used)
    debug = debug_from_comps(used, query=build_queries(item)[0])
    assert len(debug["matched_titles"]) >= 3
    assert debug["matched_prices_jpy"]
    assert debug["source_urls"][0] == auction_url("a4") or debug["source_urls"]
    assert auction_url("a1") == "https://auctions.yahoo.co.jp/jp/auction/a1"
    assert filter_comps([], item) == []
    assert quote_comps([]) == (None, [])


if __name__ == "__main__":
    test_shiny_charizard_rejects_other_sets_and_lots()
    test_koraidon_shiny_does_not_use_scarlet()
    test_card_number_and_mega()
    test_sealed_single_box_only()
    test_queries_and_fuzzy_guard()
    test_median_drops_outliers_and_empty_stays_empty()
    print("ok")
