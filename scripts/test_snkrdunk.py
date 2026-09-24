"""Offline checks for SNKRDUNK catalog matching and Yahoo vetoes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.snkrdunk import (  # noqa: E402
    choose_jp_price,
    choose_match,
    parse_condition_asks,
    parse_sales_history,
    parse_tiles,
    tile_matches,
)


_PAGE = """
<a href="https://snkrdunk.com/apparels/162095" class="t" aria-label="リザードンex SAR [SV4a 349/190](ハイクラスパック「シャイニートレジャーex」) - ¥25,900">x</a>
<a href="https://snkrdunk.com/apparels/162095" class="t" aria-label="リザードンex SAR [SV4a 349/190](ハイクラスパック「シャイニートレジャーex」) - ¥25,900">dup</a>
<a href="https://snkrdunk.com/apparels/999" class="t" aria-label="リザードンex SAR [SV3 134/108](拡張パック「黒炎の支配者」) - ¥9,000">y</a>
<a href="https://snkrdunk.com/apparels/50" class="t" aria-label="アビスアイ パック - ¥300">p</a>
<a href="https://snkrdunk.com/apparels/51" class="t" aria-label="ポケモンカードゲーム 拡張パック「アビスアイ」ボックス - ¥8,000">b</a>
<a href="https://snkrdunk.com/apparels/52" class="t" aria-label="【シュリンクなし】ポケモンカードゲーム 拡張パック「アビスアイ」ボックス - ¥5,000">o</a>
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
    assert len(tiles) == 5
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


if __name__ == "__main__":
    test_parse_and_match_printed_number()
    test_psa10_ask_and_sales_median()
    test_last_sale_replaces_yahoo_and_far_ask_blanks_it()
    print("ok")
