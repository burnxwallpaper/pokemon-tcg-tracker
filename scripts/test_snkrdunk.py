"""Offline checks for SNKRDUNK catalog matching and Yahoo vetoes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.hk_match import _card_print, _stated_rarity_conflict  # noqa: E402
from sources.snkrdunk import (  # noqa: E402
    PSA10_WEAR,
    catalog_kind,
    chart_last_sale_jpy,
    choose_jp_price,
    headline_under_min,
    liquidity_score,
    meets_min_list_price,
    product_name_ok,
    choose_match,
    official_face_matches,
    parse_condition_asks,
    parse_sales_history,
    parse_tiles,
    has_psa10_quote,
    psa10_active_ask_prices,
    psa10_last_sale_jpy,
    raw_a_ask_quote,
    raw_a_last_sale_jpy,
    recent_history_count,
    sale_within_days,
    same_print,
    sell_listing_count,
    tile_from_hottest_row,
    tile_matches,
)


_PAGE = """
<a href="https://snkrdunk.com/apparels/162095" class="t" aria-label="リザードンex SAR [SV4a 349/190](ハイクラスパック「シャイニートレジャーex」) - ¥25,900">x</a>
<a href="https://snkrdunk.com/apparels/162095" class="t" aria-label="リザードンex SAR [SV4a 349/190](ハイクラスパック「シャイニートレジャーex」) - ¥25,900">dup</a>
<a href="https://snkrdunk.com/apparels/999" class="t" aria-label="リザードンex SAR [SV3 134/108](拡張パック「黒炎の支配者」) - ¥9,000">y</a>
<a href="https://snkrdunk.com/apparels/50" class="t" aria-label="アビスアイ パック - ¥300">p</a>
<a href="https://snkrdunk.com/apparels/51" class="t" aria-label="ポケモンカードゲーム 拡張パック「アビスアイ」ボックス - ¥8,000">b</a>
<a href="https://snkrdunk.com/apparels/52" class="t" aria-label="【シュリンクなし】ポケモンカードゲーム 拡張パック「アビスアイ」ボックス - ¥5,000">o</a>
<a href="https://snkrdunk.com/apparels/880/used/42" class="t" aria-label="ピカチュウex UR [SV8 136/106] - ¥12,000">u</a>
<a href="https://snkrdunk.com/apparels/881" class="t" aria-label="Gold Necklace ネックレス - ¥9,000">n</a>
"""

_CONDS = """
{"conditionId":22,"conditionCode":"trading_card_single_psa10","filterConditionId":"psa_10","usedMinPrice":58500,"text":"PSA10","hasListing":true}
{"conditionId":23,"conditionCode":"trading_card_single_psa9","filterConditionId":"psa_9","text":"PSA9","hasListing":false}
"""


def _card(**extra: str) -> dict:
    base = {
        "kind": "psa10",
        "name_jp": "リザードンex SAR シャイニートレジャー PSA10",
        "search_jp": "リザードンex SAR PSA10 シャイニートレジャー",
        "set": "SV4a / 349/190",
    }
    base.update(extra)
    return base


def test_parse_and_match_printed_number() -> None:
    tiles = parse_tiles(_PAGE)
    assert len(tiles) == 7
    assert tiles[5]["apparel_id"] == "880"
    assert tiles[5]["number"] == "136"
    shiny = _card()
    assert tile_matches(tiles[0], shiny)
    assert not tile_matches(tiles[1], shiny)
    chosen = choose_match(tiles, shiny)
    assert chosen is not None
    assert chosen["apparel_id"] == "162095"
    box = {
        "kind": "sealed",
        "name_jp": "アビスアイ BOX 未開封",
        "search_jp": "アビスアイ BOX 未開封",
        "set": "M5",
    }
    sealed = choose_match(tiles, box)
    assert sealed is not None
    assert sealed["apparel_id"] == "51"


def test_psa10_ask_and_sales_median() -> None:
    asks = parse_condition_asks(_CONDS)
    assert asks["PSA10"] == 58500
    assert "PSA9" not in asks
    mid = parse_sales_history(
        {"history": [{"price": 8000}, {"price": 8200}, {"price": 7900}, {"price": 40000}]}
    )
    assert mid == 8000


def test_last_sale_replaces_yahoo_and_far_ask_blanks_it() -> None:
    assert choose_jp_price(63000, {"last_sale_jpy": 60000, "ask_jpy": 58000}) == (
        60000,
        "snkrdunk_last_sale",
    )
    assert choose_jp_price(63000, {"ask_jpy": 58500}) == (63000, "yahoo_auctions_jp")
    assert choose_jp_price(11111, {"ask_jpy": 45000}) == (None, "blank_yahoo_vs_snkrdunk")
    assert choose_jp_price(None, {"ask_jpy": 45000}) == (None, "empty")
    assert choose_jp_price(14000, {}) == (14000, "yahoo_auctions_jp")


def test_face_must_encode_the_print() -> None:
    assert official_face_matches(
        "https://assets.tcgdex.net/ja/SV/SV2a/201/high.webp", "SV2a", "201"
    )
    assert not official_face_matches(
        "https://www.pokemon-card.com/assets/images/card_images/large/M2a/050000_P_MGENGAEX.jpg",
        "M2a",
        "240",
    )
    assert not official_face_matches(
        "https://www.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SVP/SVP_EN_85.png",
        "SVP",
        "085",
    )


def test_catalog_kind_skips_jewelry_and_keeps_cards_and_boxes() -> None:
    tiles = parse_tiles(_PAGE)
    assert catalog_kind(tiles[5]) == "psa10"
    assert catalog_kind(tiles[3]) == "sealed"
    assert catalog_kind(tiles[6]) is None
    assert catalog_kind({"label": "リザードンex SAR [SV2a 201/165] [EN]", "set_code": "SV2a", "number": "201"}) is None


def test_zero_padded_number_and_van_gogh_promo() -> None:
    item = {
        "id": "psa10-m1l-086",
        "kind": "psa10",
        "name_jp": "リーリエの決心 SR [M1L 086/063](拡張パック「メガブレイブ」)",
        "name_zh": "リーリエの決心 SR [M1L 086/063](拡張パック「メガブレイブ」)",
        "search_jp": "リーリエの決心 SR [M1L 086/063](拡張パック「メガブレイブ」)",
        "set": "M1L / 86/063",
    }
    assert same_print(item, item["name_jp"])
    promo = {
        "id": "psa10-van-gogh-pikachu",
        "kind": "psa10",
        "name_jp": "ゴッホピカチュウ PSA10",
        "set": "SVP EN / 085",
    }
    assert product_name_ok(
        promo,
        "ピカチュウ : プロモ [SVP EN 085](「ゴッホ展」) 【英語版】",
    )


def test_set_slash_is_not_the_collector_number() -> None:
    assert _card_print({"set": "S11 / 111/100"}) == ("111", "100")
    assert _card_print({"set": "S11 / 125", "tcgdex_id": "S11-125"}) == ("125", None)
    assert _card_print({"set": "SM11 / 029/094"}) == ("029", "094")
    assert _card_print({"set": "WCS23 / 001/030"}) == ("001", "030")
    assert _card_print({"set": "S12 / 024/098"}) == ("024", "098")


def test_exact_snkrdunk_title_is_the_same_print() -> None:
    rows = [
        ("psa10-wcs23-001", "WCS23 / 001/030", "ピカチュウex [WCS23 001/030](記念デッキ)"),
        ("psa10-s11-111", "S11 / 111/100", "ギラティナV SR: SA[S11 111/100](拡張パック「ロストアビス」)"),
        ("psa10-s12-024", "S12 / 024/098", "ピカチュウ C [S12 024/098](拡張パック「パラダイムトリガー」)"),
        ("psa10-sm11-029", "SM11 / 029/094", "ミュウツー&ミュウGX RR [SM11 029/094](拡張パック「ミラクルツイン」)"),
        ("psa10-sm11-101", "SM11 / 101/094", "メガヤミラミ&バンギラスGX SR [SM11 101/094](拡張パック「ミラクルツイン」)"),
    ]
    for iid, set_field, name in rows:
        item = {"id": iid, "kind": "psa10", "name_jp": name, "search_jp": name, "set": set_field}
        assert product_name_ok(item, name), iid
        assert same_print(item, name), iid


def test_raw_a_single_fills_when_psa10_quote_is_empty() -> None:
    rows = [
        {
            "wearCount": "tradingCardSingleConditionNearlyUnused",
            "isDisplaySold": False,
            "price": 1900,
            "size": {"localizedName": "2枚"},
        },
        {
            "wearCount": "tradingCardSingleConditionNearlyUnused",
            "isDisplaySold": False,
            "price": 1000,
            "size": {"localizedName": "1枚"},
        },
        {
            "wearCount": "tradingCardSingleConditionNearlyUnused",
            "isDisplaySold": True,
            "price": 1000,
            "size": {"localizedName": "1枚"},
        },
        {
            "wearCount": "tradingCardSingleConditionNearlyUnused",
            "isDisplaySold": True,
            "price": 1200,
            "size": {"localizedName": "1枚"},
        },
        {
            "wearCount": PSA10_WEAR,
            "isDisplaySold": True,
            "price": 9000,
            "size": {"localizedName": "1枚"},
        },
        {
            "wearCount": "tradingCardSingleConditionLittleScratches",
            "isDisplaySold": True,
            "price": 800,
            "size": {"localizedName": "1枚"},
        },
    ]
    assert not has_psa10_quote([], floor_jpy=None, last_sale_jpy=None)
    assert has_psa10_quote(rows, floor_jpy=None, last_sale_jpy=psa10_last_sale_jpy(rows))
    assert psa10_last_sale_jpy(rows) == 9000
    assert raw_a_last_sale_jpy(rows) == 1100
    quote = raw_a_ask_quote(rows, floor_jpy=800)
    assert quote["ask_jpy"] == 1000
    assert quote["ask_prices_jpy"] == [1000]
    assert raw_a_ask_quote([], floor_jpy=1000)["ask_jpy"] is None


def test_psa10_last_sale_ignores_raw_and_active_asks() -> None:
    rows = [
        {"wearCount": "tradingCardSingleConditionNearlyUnused", "isDisplaySold": False, "price": 1000},
        {"wearCount": PSA10_WEAR, "isDisplaySold": False, "price": 8100},
        {"wearCount": PSA10_WEAR, "isDisplaySold": True, "price": 16000},
        {"wearCount": PSA10_WEAR, "isDisplaySold": True, "price": 15800},
    ]
    assert psa10_active_ask_prices(rows) == [8100]
    assert psa10_last_sale_jpy(rows) == 15900
    assert chart_last_sale_jpy({"points": [[1, 9000], [2, 8150]]}) == 8150


def test_sealed_history_drops_multi_box_lots() -> None:
    mid = parse_sales_history(
        {
            "history": [
                {"price": 150000, "size": "6個"},
                {"price": 24000, "size": "1個"},
                {"price": 23999, "size": "1個"},
                {"price": 245000, "size": "10個"},
            ]
        }
    )
    assert mid == 24000


def test_min_list_price_prefers_ask_then_sold() -> None:
    assert meets_min_list_price({"hk_ask_hkd": 99, "price_hkd": 500}, 100) is False
    assert meets_min_list_price({"hk_ask_hkd": None, "price_hkd": 99}, 100) is False
    assert meets_min_list_price({"hk_ask_hkd": 100, "price_hkd": 50}, 100) is True
    assert meets_min_list_price({"hk_ask_hkd": None, "price_hkd": None}, 100) is True
    assert headline_under_min({"tile_price_jpy": 2000}, fx=0.0495, minimum=100) is True
    assert headline_under_min({"tile_price_jpy": 8100}, fx=0.0495, minimum=100) is False
    assert headline_under_min({"tile_price_hkd": 50}, fx=0.0495, minimum=100) is True
    assert headline_under_min({"tile_price_hkd": 1188, "tile_price_jpy": 1000}, fx=0.0495, minimum=100) is False


def test_ur_does_not_match_sar() -> None:
    assert _stated_rarity_conflict("ピカチュウex SAR [SV8 136/106]", "ピカチュウex UR")
    assert _stated_rarity_conflict("ピカチュウex UR [SV8 132/106]", "ピカチュウex SAR")
    ur = {
        "kind": "psa10",
        "name_jp": "ピカチュウex UR PSA10",
        "search_jp": "ピカチュウex UR",
        "set": "SV8 / 136/106",
    }
    assert same_print(ur, "ピカチュウex UR [SV8 136/106]")
    assert not same_print(ur, "ピカチュウex SAR [SV8 136/106]")


def test_hottest_items_kind_floor_and_liquidity() -> None:
    card = tile_from_hottest_row(
        {
            "id": 704407,
            "name": 'MEGA Charizard X ex MUR [M2 116/080](Expansion Pack "Inferno X")',
            "minPrice": 3784,
        }
    )
    assert card is not None
    assert card["apparel_id"] == "704407"
    assert card["set_code"] == "M2"
    assert card["number"] == "116"
    assert catalog_kind(card) == "psa10"
    promo = tile_from_hottest_row(
        {"id": 618447, "name": "Fukuoka's Pikachu P [SV-P 289](Special Box)", "minPrice": 396}
    )
    assert promo is not None
    assert promo["set_code"] == "SV-P"
    assert catalog_kind(promo) == "psa10"
    box = tile_from_hottest_row(
        {
            "id": 881421,
            "name": 'Pokemon Card Game MEGA Expansion Pack "30th CELEBRATION" Box',
            "minPrice": 1188,
        }
    )
    assert catalog_kind(box) == "sealed"
    deck = tile_from_hottest_row(
        {
            "id": 881423,
            "name": 'Pokemon Card Game MEGA Constructed Deck "30th CELEBRATION Premium Deck Set"',
            "minPrice": 841,
        }
    )
    assert catalog_kind(deck) == "sealed"
    pack = tile_from_hottest_row(
        {
            "id": 881422,
            "name": 'Pokemon Card Game MEGA Expansion Pack "30th CELEBRATION" Pack',
            "minPrice": 50,
        }
    )
    assert catalog_kind(pack) is None
    assert headline_under_min(pack, fx=0.0495, minimum=100) is True
    bare = tile_from_hottest_row(
        {"id": 881427, "name": '[No shrink] Pokemon Card Game MEGA Expansion Pack "30th" Box', "minPrice": 990}
    )
    assert catalog_kind(bare) is None
    assert sale_within_days("7分前")
    assert sale_within_days("6日前")
    assert not sale_within_days("8日前")
    assert not sale_within_days("2週間前")
    assert recent_history_count(
        {"history": [{"price": 24000, "size": "1個", "date": "12分前"}, {"price": 150000, "size": "6個", "date": "1分前"}]}
    ) == 1
    assert sell_listing_count({"usedListingCount": 275, "listingCount": 0}, kind="psa10") == 275
    assert sell_listing_count({"listingCount": 1566, "usedListingCount": 0}, kind="sealed") == 1566
    assert liquidity_score(15, 275) == 99
    assert liquidity_score(0, 0, yahoo_vol=2) == 8
    assert liquidity_score(0, 4) == 6
    promo_name = "リザードン: プロモ[S8a-P 001/025](プロモカードパック 25th ANNIVERSARY edition)"
    promo_item = {
        "id": "psa10-s8a-p-001",
        "kind": "psa10",
        "name_jp": promo_name,
        "search_jp": promo_name,
        "set": "S8a-P / 001/025",
    }
    assert same_print(promo_item, promo_name)
    assert product_name_ok(promo_item, promo_name)
    assert not same_print(promo_item, "リザードン [S8a 001/025](拡張パック)")
    base = {
        "kind": "psa10",
        "name_jp": "リザードン [S8a 001/025]",
        "search_jp": "リザードン [S8a 001/025]",
        "set": "S8a / 001/025",
    }
    assert not same_print(base, promo_name)
    deck_name = "ポケモンカードゲームMEGA 構築デッキ「30th CELEBRATION プレミアムデッキセット エーフィ・ブラッキー」"
    deck_item = {
        "id": "sealed-snkr-881423",
        "kind": "sealed",
        "name_jp": deck_name,
        "search_jp": deck_name,
    }
    assert product_name_ok(deck_item, deck_name)
    assert product_name_ok(
        deck_item,
        'Pokemon Card Game MEGA Constructed Deck "30th CELEBRATION Premium Deck Set"',
    )
    box_item = {
        "kind": "sealed",
        "name_jp": "ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」ボックス",
        "search_jp": "ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」ボックス",
    }
    assert not product_name_ok(box_item, deck_name)


if __name__ == "__main__":
    test_parse_and_match_printed_number()
    test_psa10_ask_and_sales_median()
    test_last_sale_replaces_yahoo_and_far_ask_blanks_it()
    test_face_must_encode_the_print()
    test_catalog_kind_skips_jewelry_and_keeps_cards_and_boxes()
    test_zero_padded_number_and_van_gogh_promo()
    test_set_slash_is_not_the_collector_number()
    test_exact_snkrdunk_title_is_the_same_print()
    test_raw_a_single_fills_when_psa10_quote_is_empty()
    test_psa10_last_sale_ignores_raw_and_active_asks()
    test_sealed_history_drops_multi_box_lots()
    test_min_list_price_prefers_ask_then_sold()
    test_ur_does_not_match_sar()
    test_hottest_items_kind_floor_and_liquidity()
    print("ok")
