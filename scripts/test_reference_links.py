"""Offline checks for quote labels, WTB bids, and reference URLs."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources.hk_match import lowest_ask, match_listings  # noqa: E402
from sources.reference_links import (  # noqa: E402
    attach_public_quotes,
    best_bid,
    build_reference_links,
    hkcardlink_listing_url,
)


def test_hkcardlink_listing_url_uses_name_and_id_prefix() -> None:
    from urllib.parse import quote

    url = hkcardlink_listing_url("PSA10 噴火龍", "abcdef12-3456-7890-abcd-ef1234567890")
    assert url == "https://www.hkcardlink.com/listing/" + quote("psa10-噴火龍-abcdef12", safe="")
    assert hkcardlink_listing_url("", "abcdef12-3456-7890-abcd-ef1234567890") is None


def test_lowest_ask_matches_single_price() -> None:
    assert lowest_ask([1880]) == 1880
    assert lowest_ask([900, 1200, 1500]) == 900
    assert lowest_ask([]) is None


def test_best_bid_ignores_sells_and_empty_prices() -> None:
    price, row = best_bid(
        [
            {"listing_type": "sale", "price_hkd": 5000, "source": "hkcardlink"},
            {"listing_type": "wtb", "price_hkd": 0, "source": "hkcardlink"},
            {"listing_type": "wtb", "price_hkd": 3200, "url": "https://www.hkcardlink.com/listing/a"},
            {"listing_type": "wtb", "price_hkd": 2800},
        ]
    )
    assert price == 3200
    assert row is not None
    assert row["url"].endswith("/listing/a")
    assert best_bid([{"price_hkd": 999, "source": "carousell_hk"}]) == (None, None)


def test_reference_links_use_keywords_and_real_listing() -> None:
    links = build_reference_links(
        {
            "name_zh": "噴火龍ex SAR PSA10",
            "name_jp": "リザードンex SAR PSA10",
            "kind": "psa10",
            "sources": ["yahoo_auctions_jp", "lono"],
        },
        watch={"search_jp": "リザードンex SAR PSA10", "search_hk": "噴火龍 SAR PSA10"},
        listings=[
            {
                "source": "hkcardlink",
                "listing_type": "wtb",
                "price_hkd": 4000,
                "url": "https://www.hkcardlink.com/listing/charizard-wtb",
            }
        ],
    )
    labels = [link["label"] for link in links]
    assert labels[0] == "HKCardLink 徵求"
    assert any(link["href"].startswith("https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=") for link in links)
    assert any("carousell.com.hk/search/" in link["href"] and "%E5%99%B4" in link["href"] for link in links)
    assert any(link["label"] == "LONO" for link in links)
    assert any(link["label"] == "HKCardLink 搜尋" for link in links)
    assert sum(1 for link in links if link["label"] == "HKCardLink 徵求") == 1


def test_attach_does_not_invent_low_or_bid() -> None:
    single = attach_public_quotes(
        {"id": "a", "name_zh": "甲", "name_jp": "ア", "hk_ask_hkd": 500, "hk_listings_n": 1, "sources": []},
        bid_hkd=None,
    )
    assert single["hk_ask_low_hkd"] == 500
    assert single["hk_bid_hkd"] is None
    many = attach_public_quotes(
        {"id": "b", "name_zh": "乙", "name_jp": "イ", "hk_ask_hkd": 500, "hk_listings_n": 4, "sources": []},
        bid_hkd=None,
    )
    assert many["hk_ask_low_hkd"] is None
    assert many["hk_bid_hkd"] is None
    assert many["links"]


def test_match_listings_keeps_url_and_wtb_type() -> None:
    hits = match_listings(
        [
            {
                "card_name": "PSA10 噴火龍ex SAR",
                "price": 5100,
                "source": "hkcardlink",
                "listing_type": "wtb",
                "url": "https://www.hkcardlink.com/listing/zard",
                "id": "1",
            }
        ],
        keyword="噴火龍 SAR PSA10",
        kind="psa10",
        name_zh="噴火龍ex SAR PSA10",
    )
    assert len(hits) == 1
    assert hits[0]["listing_type"] == "wtb"
    assert hits[0]["url"].endswith("/listing/zard")


if __name__ == "__main__":
    test_hkcardlink_listing_url_uses_name_and_id_prefix()
    test_lowest_ask_matches_single_price()
    test_best_bid_ignores_sells_and_empty_prices()
    test_reference_links_use_keywords_and_real_listing()
    test_attach_does_not_invent_low_or_bid()
    test_match_listings_keeps_url_and_wtb_type()
    print("ok")
