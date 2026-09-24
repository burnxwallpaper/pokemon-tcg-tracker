"""Offline checks for HK title matching and Carousell listingCards parsing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.carousell_hk import parse_listing_cards  # noqa: E402
from sources.hk_match import match_listings, primary_query, robust_median  # noqa: E402
from sources.hk_shops import parse_lono_cards  # noqa: E402


def _item(kind: str, zh: str, jp: str, hk: str) -> dict:
    return {"kind": kind, "name_zh": zh, "name_jp": jp, "search_hk": hk}


def test_listing_cards_ignores_empty_price() -> None:
    html = (
        '{"listingCards":['
        '{"title":"PSA10 Charizard 151 SAR 噴火龍","price":"HK$5,200","listingID":11},'
        '{"title":"","price":"HK$9","listingID":0},'
        '{"title":"noise","price":"","listingID":12}'
        "]}"
    )
    rows = parse_listing_cards(html)
    assert len(rows) == 1
    assert rows[0]["price"] == 5200
    assert rows[0]["card_name"].startswith("PSA10")


def test_charizard_variants_do_not_cross_match() -> None:
    rows = [
        {"card_name": "PSA10 噴火龍ex SAR 151", "price": 5000},
        {"card_name": "PSA10 Mega Charizard X ex SAR 噴火龍X", "price": 8000},
        {"card_name": "PSA10 Mega Charizard X ex SR 噴火龍X", "price": 500},
        {"card_name": "PSA10 噴火龍 黑炎 SAR", "price": 4200},
        {"card_name": "噴火龍ex SAR 151", "price": 900},
        {"card_name": "PSA10 噴火龍 皮卡丘 超夢 一套", "price": 2600},
    ]
    z151 = match_listings(
        rows,
        keyword="噴火龍 SAR PSA10 151",
        kind="psa10",
        name_zh="噴火龍 ex SAR PSA10",
        name_jp="リザードンex SAR PSA10",
    )
    assert [h["price_hkd"] for h in z151] == [5000]
    mega = match_listings(
        rows,
        keyword="超級噴火龍X SAR PSA10",
        kind="psa10",
        name_zh="超級噴火龍X ex SAR PSA10",
        name_jp="メガリザードンXex SAR PSA10",
    )
    assert [h["price_hkd"] for h in mega] == [8000]


def test_sealed_skips_case_dx_and_traditional_chinese() -> None:
    rows = [
        {"card_name": "Pokémon Booster Box (JP) - Storm Emeralda (M6) - 30 Packs", "price": 1230},
        {"card_name": "Pokémon Booster Box (JP) - Storm Emeralda Case - 20 Boxes", "price": 24000},
        {"card_name": "Pokémon Booster Box (JP) - White Flare DX (SV11W DX)", "price": 1699},
        {"card_name": "Pokémon Booster Box (JP) - White Flare (SV11W) - 20 Packs", "price": 1449},
        {"card_name": "風暴翡翠 繁中 原盒", "price": 480},
    ]
    storm = match_listings(
        rows,
        keyword="風暴翡翠 BOX 未開封",
        kind="sealed",
        name_zh="風暴翡翠 BOX（未開封）",
        name_jp="ストームエメラルダ BOX 未開封",
    )
    assert [h["price_hkd"] for h in storm] == [1230]
    flare = match_listings(
        rows,
        keyword="白炎 BOX 未開封",
        kind="sealed",
        name_zh="白炎 BOX（未開封）",
        name_jp="ホワイトフレア BOX 未開封",
    )
    assert [h["price_hkd"] for h in flare] == [1449]


def test_base_gengar_skips_mega_and_eevee_skips_umbreon() -> None:
    rows = [
        {"card_name": "PSA10 Mega Gengar ex 超級耿鬼", "price": 3000},
        {"card_name": "PSA10 耿鬼 ex SAR", "price": 1500},
        {"card_name": "PSA10 月亮伊布 ex SAR Umbreon", "price": 4000},
        {"card_name": "PSA10 伊布 ex SAR Eevee", "price": 800},
    ]
    gengar = match_listings(
        rows, keyword="耿鬼 SAR PSA10", kind="psa10", name_zh="耿鬼 ex SAR PSA10", name_jp="ゲンガーex SAR PSA10"
    )
    assert [h["price_hkd"] for h in gengar] == [1500]
    eevee = match_listings(
        rows, keyword="伊布 ex SAR PSA10", kind="psa10", name_zh="伊布 ex SAR PSA10", name_jp="イーブイex SAR PSA10"
    )
    assert [h["price_hkd"] for h in eevee] == [800]


def test_lono_card_html() -> None:
    html = """
    <div class="title text-primary-color ">2025 POKEMON JAPANESE M2A MEGA CHARIZARD X EX 【PSA 10】</div>
    <div class="quick-cart-price ">
      <span class="global-primary dark-primary sl-price price">HK$13,000.00</span>
    </div>
    """
    rows = parse_lono_cards(html)
    assert len(rows) == 1
    assert rows[0]["price"] == 13000


def test_shiny_mew_rejects_151_listing() -> None:
    rows = [{
        "card_name": "PTCG Pokemon Card SV2a PSA10 日版 夢幻 EX SAR 205/165",
        "price": 3000,
    }]
    item_kw = "夢幻 SAR PSA10 SV4a-347"
    hits = match_listings(
        rows, keyword=item_kw, kind="psa10", name_zh="夢幻 ex SAR PSA10", name_jp="ミュウex SAR PSA10"
    )
    assert hits == []


def test_black_flame_box_skips_gift_set() -> None:
    rows = [
        {"card_name": "【PTCG】Pokemon Card Game SV3「黑炎的支配者」BOX（原盒未開封）", "price": 988},
        {"card_name": "Japanese Charizard Box 噴火龍擴充禮盒 SV3 黑炎支配者 日版", "price": 500},
        {"card_name": "SV03 OBSIDIAN FLAMES 黑炎支配者 Booster Box 英文版", "price": 860},
        {"card_name": "日版 原箱(12盒) SV3 黑炎の支配者", "price": 14200},
    ]
    hits = match_listings(
        rows,
        keyword="黑炎 BOX 未開封 SV3",
        kind="sealed",
        name_zh="黑炎支配者 BOX（未開封）",
        name_jp="黒炎の支配者 BOX 未開封",
    )
    assert [h["price_hkd"] for h in hits] == [988]


def test_multi_card_menu_and_m2a_are_rejected() -> None:
    menu = {
        "card_name": "PSA10 151 SV2A 噴火龍 185/165 SR 比卡超 耿鬼 SAR",
        "price": 1000,
    }
    hits = match_listings(
        [menu],
        keyword="噴火龍 SAR PSA10 151 sv2a",
        kind="psa10",
        name_zh="噴火龍 ex SAR PSA10",
        name_jp="リザードンex SAR PSA10",
    )
    assert hits == []
    wrong_set = {
        "card_name": "噴火龍 M2A PSA10 MEGA CHARIZARD X ex SAR",
        "price": 6500,
    }
    hits = match_listings(
        [wrong_set],
        keyword="超級噴火龍X SAR PSA10 M2",
        kind="psa10",
        name_zh="超級噴火龍X ex SAR PSA10",
        name_jp="メガリザードンXex SAR PSA10",
    )
    assert hits == []


def test_primary_query_and_median() -> None:
    item = _item("psa10", "超級噴火龍X ex SAR PSA10", "メガリザードンXex SAR PSA10", "超級噴火龍X SAR PSA10")
    assert "噴火龍" in primary_query(item)
    assert robust_median([100, 120, 110, 5000]) == 110


if __name__ == "__main__":
    test_listing_cards_ignores_empty_price()
    test_charizard_variants_do_not_cross_match()
    test_sealed_skips_case_dx_and_traditional_chinese()
    test_base_gengar_skips_mega_and_eevee_skips_umbreon()
    test_lono_card_html()
    test_primary_query_and_median()
    print("ok")
