"""HK shop catalogs are not collected.

The HKD sell ask is the SNKRDUNK active book converted at fx_jpy_to_hkd.
These names stay listed so a preserved snapshot cannot copy them back into
sources, hk_backend, or source_status.
"""
from __future__ import annotations

DROPPED_HK_SOURCES = frozenset(
    {
        "carousell_hk",
        "hkcardlink",
        "lono",
        "zenox",
        "shipmytoy",
        "facebook_hk",
        "hk_card_shops",
        "mercari_jp",
        "cardrush",
        "yuyu_tei",
        "magi",
    }
)
