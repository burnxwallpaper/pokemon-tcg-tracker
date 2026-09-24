"""Offline checks for HK title matching and Carousell listingCards parsing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.carousell_hk import parse_listing_cards  # noqa: E402
from sources.hk_match import (  # noqa: E402
    lowest_ask,
    match_item,
    match_listings,
    primary_query,
    publish_ask,
    robust_median,
)
from sources.hk_shops import parse_lono_cards, parse_shopline_cards, parse_zenox_products, sell_price  # noqa: E402
from sources.snkrdunk import (  # noqa: E402
    choose_hit,
    psa10_market_jpy,
    same_print,
    search_keyword,
    sealed_market_jpy,
)
from sources.yahoo_auctions_jp import publish_sold_median  # noqa: E402


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
    assert lowest_ask([100, 120, 110, 5000]) == 100


def test_specific_names_seek_grade_and_card_number() -> None:
    rows = [
        {"card_name": "PSA10 超夢 ex SAR", "price": 900},
        {"card_name": "PSA10 火箭隊超夢 ex SAR", "price": 3200},
        {"card_name": "收 PSA10 火箭隊超夢 SAR 預算", "price": 2500},
        {"card_name": "PSA9 火箭隊超夢 ex SAR", "price": 1800},
        {"card_name": "PSA10 噴火龍ex SAR 151/165", "price": 4000},
        {"card_name": "PSA10 噴火龍ex SAR Pokemon 151 201/165", "price": 7800},
        {"card_name": "PSA10 噴火龍ex SAR Pokemon 151 185/165", "price": 2100},
        {"card_name": "WTB Charizard 151 PSA10", "price": 5000, "listing_type": "want"},
    ]
    rocket = match_listings(
        rows,
        keyword="火箭隊超夢 SAR PSA10",
        kind="psa10",
        name_zh="火箭隊超夢 ex SAR PSA10",
        name_jp="ロケット団のミュウツーex SAR PSA10",
    )
    assert [h["price_hkd"] for h in rocket] == [3200]
    z151 = match_listings(
        rows,
        keyword="噴火龍 SAR PSA10 151",
        kind="psa10",
        name_zh="噴火龍 ex SAR PSA10",
        card_number="201",
    )
    assert [h["price_hkd"] for h in z151] == [7800]
    ar = match_listings(
        [{"card_name": "PSA10 Pikachu AR Holo 173/165 promo sar", "price": 930}],
        keyword="皮卡丘 SAR PSA10 151 sv2a",
        kind="psa10",
        name_zh="皮卡丘 ex SAR PSA10",
        card_number="198",
        card_denom="165",
    )
    assert ar == []
    wrong_set = match_listings(
        [{"card_name": "PSA10 PTCG M2a 奇樹 SAR", "price": 500}],
        keyword="奇樹 SAR PSA10 sv2d",
        kind="psa10",
        name_zh="奇樹 SAR PSA10",
    )
    assert wrong_set == []
    menu = match_listings(
        [
            {"card_name": "原盒日文英文Pokemon booster box , sv9a, s8, fusion strike", "price": 900},
            {"card_name": "Pokémon Chinese Exclusive 151 Figurine Box Set", "price": 150},
            {"card_name": "日版原盒 Pokémon Card 151 Booster Box Japanese", "price": 2400},
        ],
        keyword="151 BOX 未開封 sv2a",
        kind="sealed",
        name_zh="151 補充包 BOX（未開封）",
        name_jp="ポケモンカード151 BOX 未開封",
    )
    assert [h["price_hkd"] for h in menu] == [2400]


def test_mega_dream_box_does_not_need_set_code_on_the_title() -> None:
    rows = [
        {"card_name": "Pokemon TCG日版 M2A ドリームEX Booster Box", "price": 780},
        {"card_name": "Pokemon TCG日版 超級夢想 Booster Box", "price": 760},
        {"card_name": "Pokemon TCG日版 M2 MEGA烈焰 Booster Box", "price": 900},
    ]
    hits = match_listings(
        rows,
        keyword="超級夢想 BOX 未開封 M2a",
        kind="sealed",
        name_zh="超級夢想 ex BOX（未開封）",
        name_jp="メガドリームex BOX 未開封",
    )
    assert [h["price_hkd"] for h in hits] == [760, 780]


def test_pack_price_is_not_the_box_ask() -> None:
    assert sell_price("Booster Box", [25, 700]) == 700
    assert sell_price("Booster Box", [1150, 1350]) == 1150
    html = """
    <div class="title text-primary-color ">Pokemon TCG日版 M5 深淵之瞳 Booster Box</div>
    HK$20.00 HK$550.00
    <div class="title text-primary-color ">Pokemon TCG日版 M6 綠寶石風暴 Booster Box</div>
    售完 HK$1,199.00
    """
    rows = parse_shopline_cards(html, "shipmytoy")
    assert [(r["card_name"], r["price"]) for r in rows] == [
        ("Pokemon TCG日版 M5 深淵之瞳 Booster Box", 550),
    ]


def test_zenox_psa10_skips_psa9_and_sold_out() -> None:
    payload = {
        "products": [
            {
                "id": 1,
                "title": "Pokemon - Charizard ex (JP) 201/165",
                "variants": [
                    {"title": "PSA 9", "available": True, "price": "4200.00"},
                    {"title": "PSA 10", "available": True, "price": "7520.00"},
                    {"title": "PSA 10", "available": False, "price": "1000.00"},
                ],
            },
            {
                "id": 2,
                "title": "Pokemon - Pikachu (CN) 171/151",
                "variants": [{"title": "PSA 10", "available": True, "price": "300.00"}],
            },
        ]
    }
    rows = parse_zenox_products(payload, graded=True)
    assert len(rows) == 2
    assert rows[0]["price"] == 7520
    assert "PSA10" in rows[0]["card_name"]
    item = {
        "kind": "psa10",
        "name_zh": "噴火龍 ex SAR PSA10",
        "name_jp": "リザードンex SAR PSA10",
        "search_hk": "噴火龍 SAR PSA10 151",
        "set": "sv2a / 201/165",
        "tcgdex_id": "SV2a-201",
    }
    hits = match_item(rows, item)
    assert [h["price_hkd"] for h in hits] == [7520]


def test_mew_and_mewtwo_do_not_share_a_substring() -> None:
    rows = [
        {"card_name": "PSA10 超夢 ex SAR ミュウツー", "price": 900},
        {"card_name": "PSA10 夢幻 ex SAR ミュウ SV4a 347/190", "price": 7000},
        {"card_name": "PSA10 Mewtwo ex SAR", "price": 1100},
    ]
    mew = match_listings(
        rows,
        keyword="夢幻 SAR PSA10 sv4a",
        kind="psa10",
        name_zh="夢幻 ex SAR PSA10",
        name_jp="ミュウex SAR PSA10",
        card_number="347",
    )
    assert [h["price_hkd"] for h in mew] == [7000]
    mewtwo = match_listings(
        rows,
        keyword="超夢 SAR PSA10",
        kind="psa10",
        name_zh="超夢 ex SAR PSA10",
        name_jp="ミュウツーex SAR PSA10",
    )
    assert [h["price_hkd"] for h in mewtwo] == [900, 1100]


def test_charizard_without_set_or_number_is_rejected() -> None:
    rows = [
        {"card_name": "PSA10 噴火龍ex SAR", "price": 3000},
        {"card_name": "PSA10 噴火龍 黑炎 SAR SV3", "price": 4200},
        {"card_name": "PSA10 Mega Charizard X ex SAR 噴火龍X", "price": 8000},
        {"card_name": "PSA10 噴火龍ex SAR Pokemon 151 201/165", "price": 5500},
    ]
    hits = match_listings(
        rows,
        keyword="噴火龍 SAR PSA10 sv2a",
        kind="psa10",
        name_zh="噴火龍 ex SAR PSA10",
        name_jp="リザードンex SAR PSA10",
        card_number="201",
        card_denom="165",
    )
    assert [h["price_hkd"] for h in hits] == [5500]
    assert hits[0]["strong"] is True


def test_listing_must_match_the_card_in_the_name() -> None:
    import json
    from pathlib import Path

    cfg = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in cfg["watchlist"]}
    pikachu = by_id["psa10-pikachu-ex-sar-151"]
    assert pikachu["tcgdex_id"] == "SV2a-173"
    assert "173/165" in pikachu["set"]
    assert "AR" in pikachu["name_zh"]
    gengar = by_id["psa10-gengar-ex-sar"]
    assert "088/071" in gengar["set"]
    assert "SR" in gengar["name_jp"]
    iono = by_id["psa10-iono-sar"]
    assert iono["tcgdex_id"] == "SV2D-096"
    assert "096/071" in iono["set"]
    assert "350" not in iono["set"]
    moon = by_id["psa10-eevee-heroes-box-promo"]
    assert "085/069" in moon["set"]
    assert "ブラッキーV" in moon["name_jp"]
    zoro = by_id["psa10-n-sar"]
    assert "ゾロアーク" in zoro["name_jp"]
    assert "127/100" in zoro["set"]
    urls = [row.get("image_official_url") for row in cfg["watchlist"]]
    assert len(urls) == len(set(urls))

    rows = [
        {"card_name": "PSA10 皮卡丘 ex SAR 198/165", "price": 4000, "id": "sar"},
        {"card_name": "PSA10 皮卡丘 AR 173/165 151", "price": 1800, "id": "ar"},
        {"card_name": "PSA10 ゲンガーex SAR 088/071", "price": 900, "id": "gsar"},
        {"card_name": "PSA10 ゲンガーex SR 088/071", "price": 2200, "id": "gsr"},
        {"card_name": "PSA10 N SAR 350", "price": 500, "id": "n"},
        {"card_name": "PSA10 Nのゾロアークex SAR 127/100", "price": 1600, "id": "zoro"},
        {"card_name": "PSA10 ナンジャモ SAR 350/190 シャイニートレジャー", "price": 1400, "id": "shiny"},
        {"card_name": "PSA10 ナンジャモ SAR 096/071 クレイバースト", "price": 3200, "id": "clay"},
        {"card_name": "PSA10 ブラッキーex SAR 217/187", "price": 3600, "id": "ex"},
        {"card_name": "PSA10 ブラッキーV 085/069 イーブイヒーローズ", "price": 8000, "id": "moon"},
    ]
    assert [h["id"] for h in match_item(rows, pikachu)] == ["ar"]
    assert [h["id"] for h in match_item(rows, gengar)] == ["gsr"]
    assert [h["id"] for h in match_item(rows, zoro)] == ["zoro"]
    assert [h["id"] for h in match_item(rows, iono)] == ["clay"]
    assert [h["id"] for h in match_item(rows, moon)] == ["moon"]


def test_yahoo_sold_requires_grade_set_and_enough_comps() -> None:
    item = {
        "kind": "psa10",
        "name_zh": "奇樹 SAR PSA10",
        "name_jp": "ナンジャモ SAR PSA10",
        "search_jp": "ナンジャモ SAR PSA10",
        "set": "sv2a / 350/165",
        "tcgdex_id": "SV2D-096",
    }
    rows = [
        {"card_name": "ナンジャモ SAR PSA10", "price": 18000, "id": "a"},
        {"card_name": "ナンジャモ SAR PSA9", "price": 9000, "id": "b"},
        {"card_name": "ナンジャモ sv2D 096/071 SAR PSA10", "price": 17500, "id": "c"},
        {"card_name": "ナンジャモ sv2D 096/071 SAR PSA10", "price": 18200, "id": "d"},
        {"card_name": "ナンジャモ sv2a 350/165 SAR PSA10", "price": 80000, "id": "e"},
        {"card_name": "ナンジャモ sv2D 096/071 SAR PSA10", "price": 400, "id": "f"},
    ]
    from sources.hk_match import match_item

    hits = match_item(
        rows,
        item,
        apply_price_band=False,
        require_print=True,
        extra_query=item["search_jp"],
    )
    assert sorted(h["id"] for h in hits) == ["c", "d", "f"]
    assert publish_sold_median([17500, 18200, 400]) == 17500
    assert publish_sold_median([17500, 18200]) is None
    sealed = {
        "kind": "sealed",
        "name_zh": "151 補充包 BOX（未開封）",
        "name_jp": "ポケモンカード151 BOX 未開封",
        "search_jp": "ポケモンカード151 BOX 未開封",
        "set": "SV2a",
    }
    box_rows = [
        {"card_name": "ポケモンカード151 未開封 BOX シュリンク付き", "price": 48000, "id": "box"},
        {"card_name": "ポケモンカード151 パック 未開封", "price": 800, "id": "pack"},
        {"card_name": "ポケモンカード151 カートン 未開封", "price": 500000, "id": "case"},
        {"card_name": "ピカチュウex SAR PSA10 151", "price": 90000, "id": "card"},
    ]
    box_hits = match_item(box_rows, sealed, apply_price_band=False, extra_query=sealed["search_jp"])
    assert [h["id"] for h in box_hits] == ["box"]
    lots = match_item(
        [
            {"card_name": "ポケモンカード151 2BOX シュリンク付き", "price": 90000, "id": "two"},
            {"card_name": "メガブレイブ メガシンフォニア 各2BOX", "price": 29000, "id": "combo"},
            {"card_name": "ポケモンカード151 1BOX 新品未開封 シュリンク付き", "price": 48000, "id": "one"},
        ],
        sealed,
        apply_price_band=False,
        extra_query=sealed["search_jp"],
    )
    assert [h["id"] for h in lots] == ["one"]


def test_bare_collector_number_must_match() -> None:
    wrong = match_listings(
        [{"card_name": "寶可夢卡 sv5k 097 耿鬼sar psa10", "price": 2000}],
        keyword="耿鬼 SAR PSA10 sv5k",
        kind="psa10",
        name_zh="耿鬼 ex SAR PSA10",
        card_number="088",
    )
    assert wrong == []
    right = match_listings(
        [{"card_name": "PSA10 耿鬼 sv5k 088 SAR", "price": 3000}],
        keyword="耿鬼 SAR PSA10 sv5k",
        kind="psa10",
        name_zh="耿鬼 ex SAR PSA10",
        card_number="088",
    )
    assert [h["price_hkd"] for h in right] == [3000]


def test_publish_ask_prefers_median_and_drops_a_lone_weak_listing() -> None:
    listings = [
        {"price_hkd": 1000, "strong": False, "url": "https://example.test/a", "title": "a", "id": "a"},
        {"price_hkd": 1100, "strong": False, "url": "https://example.test/b", "title": "b", "id": "b"},
        {"price_hkd": 50, "strong": False, "url": "https://example.test/c", "title": "c", "id": "c"},
        {"price_hkd": 9000, "strong": False, "url": "https://example.test/d", "title": "d", "id": "d"},
    ]
    published = publish_ask(listings, 1000)
    assert published["hkd"] == 1050
    assert published["match_count"] == 2
    assert published["example_url"] in ("https://example.test/a", "https://example.test/b")
    lone = publish_ask(
        [{"price_hkd": 900, "strong": False, "url": "https://example.test/z", "id": "z"}],
        1000,
    )
    assert lone["hkd"] is None
    strong = publish_ask(
        [{"price_hkd": 900, "strong": True, "url": "https://example.test/s", "id": "s"}],
        1000,
    )
    assert strong["hkd"] == 900
    assert strong["match_count"] == 1
    absurd = publish_ask(
        [{"price_hkd": 50, "strong": True, "url": "https://example.test/bad", "id": "bad"}],
        1000,
    )
    assert absurd["hkd"] is None


def test_snkrdunk_print_rejects_english_reprint_and_loose_box() -> None:
    pikachu = {
        "kind": "psa10",
        "name_zh": "皮卡丘 AR（151）PSA10",
        "name_jp": "ピカチュウ AR PSA10",
        "search_jp": "ピカチュウ AR PSA10 173/165 ポケモンカード151",
        "search_hk": "皮卡丘 AR PSA10 151",
        "set": "sv2a / 173/165",
        "tcgdex_id": "SV2a-173",
    }
    charizard = {
        "kind": "psa10",
        "name_zh": "噴火龍 ex SAR（151）PSA10",
        "name_jp": "リザードンex SAR PSA10 151",
        "search_jp": "リザードンex SAR PSA10 201/165",
        "search_hk": "噴火龍 SAR PSA10 151",
        "set": "sv2a / 201/165",
        "tcgdex_id": "SV2a-201",
    }
    box = {
        "kind": "sealed",
        "name_zh": "151 補充包 BOX（未開封）",
        "name_jp": "ポケモンカード151 BOX 未開封",
        "search_jp": "ポケモンカード151 BOX 未開封 シュリンク",
        "search_hk": "151 BOX 未開封",
        "set": "SV2a",
    }
    assert search_keyword(pikachu) == "sv2a 173"
    assert search_keyword(box) == "ポケモンカード151 BOX"
    assert search_keyword(
        {
            "kind": "psa10",
            "name_jp": "Nのゾロアークex SAR PSA10",
            "set": "SV9 / 127/100",
            "tcgdex_id": "SV9-127",
        }
    ) == "sv9 127"
    assert search_keyword(
        {
            "kind": "psa10",
            "name_jp": "ギラティナVSTAR UR PSA10",
            "set": "S11 / 125",
            "tcgdex_id": "S11-125",
        }
    ) == "s11 125"
    assert same_print(
        {
            "kind": "psa10",
            "name_jp": "シロナの覇気 SAR PSA10",
            "name_zh": "竹蘭的霸氣 SAR PSA10",
            "search_jp": "シロナの覇気 SAR PSA10",
            "search_hk": "竹蘭的霸氣 SAR PSA10",
            "set": "S12a / 239",
            "tcgdex_id": "S12a-239",
        },
        'Cynthia’s Ambition SAR[s12a 239/172](High Class Pack "VSTAR Universe")',
    )
    assert same_print(
        {
            "kind": "psa10",
            "name_jp": "ミモザ SAR PSA10",
            "name_zh": "米莫莎 SAR PSA10",
            "search_jp": "ミモザ SAR PSA10",
            "search_hk": "米莫莎 SAR PSA10",
            "set": "SV1V / 105",
            "tcgdex_id": "SV1V-105",
        },
        'Miriam SAR[SV1V 105/078](Scarlet & Violet Expansion Pack "Violet ex")',
    )
    assert same_print(pikachu, "Pikachu AR[SV2a 173/165]")
    assert not same_print(pikachu, "Pikachu AR[SV2a 198/165]")
    assert not same_print(charizard, "Alakazam[MEW EN 201/165]")
    assert not same_print(charizard, "Charizard ex SAR[MEW EN 199/165]")
    assert same_print(charizard, "Charizard ex SAR[SV2a 201/165]")
    hit = choose_hit(
        charizard,
        [
            {"id": 1, "name": "Alakazam[MEW EN 201/165]"},
            {"id": 2, "name": "Charizard ex SAR[MEW EN 199/165]"},
            {"id": 128117, "name": "Charizard ex SAR[SV2a 201/165]"},
        ],
    )
    assert hit is not None and hit["id"] == 128117
    boxed = choose_hit(
        box,
        [
            {"id": 9, "name": '[No shrink] Pokemon Card Game Scarlet & Violet Enhanced Expansion Pack "pokemon card 151" Box'},
            {"id": 8, "name": "【ポケカ 100BOX 抽選定価販売】「ポケモンカード151」20BOX"},
            {"id": 7, "name": "Pokemon Card Game [EN Ver.] Scarlet & Violet 151 Pokemon Center Elite Trainer Box"},
            {"id": 118914, "name": 'Pokemon Card Game Scarlet & Violet Enhanced Expansion Pack "pokemon card 151" Box'},
        ],
    )
    assert boxed is not None and boxed["id"] == 118914


def test_snkrdunk_psa10_market_ignores_raw_and_other_grades() -> None:
    psa10 = "tradingCardSingleConditionPSA10"
    mid = psa10_market_jpy(
        [
            {"wearCount": psa10, "price": 12800, "isDisplaySold": False},
            {"wearCount": psa10, "price": 12700, "isDisplaySold": False},
            {"wearCount": psa10, "price": 13000, "isDisplaySold": False},
            {"wearCount": psa10, "price": 12699, "isDisplaySold": True},
            {"wearCount": "raw", "price": 3500, "isDisplaySold": False},
            {"wearCount": "psa9", "price": 8000, "isDisplaySold": False},
        ]
    )
    assert mid == 12800
    thin = psa10_market_jpy(
        [
            {"wearCount": psa10, "price": 12800, "isDisplaySold": False},
            {"wearCount": psa10, "price": 12000, "isDisplaySold": True},
            {"wearCount": psa10, "price": 14000, "isDisplaySold": True},
        ]
    )
    assert thin == 12800
    assert psa10_market_jpy([{"wearCount": psa10, "price": 12800, "isDisplaySold": False}]) is None
    assert sealed_market_jpy({"minPrice": 45000, "usedMinPrice": 40000}) == 45000
    assert sealed_market_jpy({"minPrice": 0, "usedMinPrice": 40000}) == 40000


if __name__ == "__main__":
    test_listing_cards_ignores_empty_price()
    test_charizard_variants_do_not_cross_match()
    test_sealed_skips_case_dx_and_traditional_chinese()
    test_base_gengar_skips_mega_and_eevee_skips_umbreon()
    test_lono_card_html()
    test_shiny_mew_rejects_151_listing()
    test_black_flame_box_skips_gift_set()
    test_multi_card_menu_and_m2a_are_rejected()
    test_primary_query_and_median()
    test_specific_names_seek_grade_and_card_number()
    test_mega_dream_box_does_not_need_set_code_on_the_title()
    test_pack_price_is_not_the_box_ask()
    test_zenox_psa10_skips_psa9_and_sold_out()
    test_mew_and_mewtwo_do_not_share_a_substring()
    test_charizard_without_set_or_number_is_rejected()
    test_listing_must_match_the_card_in_the_name()
    test_yahoo_sold_requires_grade_set_and_enough_comps()
    test_bare_collector_number_must_match()
    test_publish_ask_prefers_median_and_drops_a_lone_weak_listing()
    test_snkrdunk_print_rejects_english_reprint_and_loose_box()
    test_snkrdunk_psa10_market_ignores_raw_and_other_grades()
    print("ok")
