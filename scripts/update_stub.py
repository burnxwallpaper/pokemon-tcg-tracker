#!/usr/bin/env python3
"""
update_stub.py — Pokémon TCG price tracker update pipeline STUB

Pipeline (documented; real fetch not implemented yet):
  1. fetch   — pull listings/sold comps from enabled sources in config.json
  2. normalize — convert all prices to HKD via fx_jpy_to_hkd; unify schema
  3. compute — 1-day / 7-day movers, liquidity ranks, JP↔HK spreads
  4. write   — data/latest.json + data/history/YYYY-MM-DD.json
               + data/history/series/{id}.json (~90 daily points)

This stub only regenerates SAMPLE (範例) data from config so the dashboard works.
No network scraping. Flip source flags and replace generate_sample_* later.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from sources.reference_links import attach_public_quotes  # noqa: E402
CONFIG_PATH = ROOT / "config.json"
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_DIR = ROOT / "data" / "history"
SERIES_DIR = HISTORY_DIR / "series"

# Asia/Hong_Kong = UTC+8
HK_TZ = timezone(timedelta(hours=8))


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def hkd(jpy: float, fx: float) -> float:
    return round(jpy * fx, 2)


def generate_history(
    *,
    days: int,
    end: datetime,
    price_hkd: float,
    hk_ask_hkd: float | None,
    short_pct: float,
    med_pct: float,
    vol_today: int,
    vol_7d: float,
    seed: int,
) -> list[dict]:
    """Synthesize ~days daily points ending at `end` (HK calendar).

    Walks backward from today's prices using short/med drift and a light
    deterministic wobble so each sample series looks distinct.
    Shape: {date, price_hkd, hk_ask_hkd, volume}
    """
    points: list[dict] = []
    # Approximate daily drift from 7d move; 1d move used as recent bias.
    daily_drift = (med_pct / 100.0) / max(days - 1, 1)
    recent_bias = (short_pct / 100.0) / 7.0

    for i in range(days):
        # i=0 is oldest, i=days-1 is today
        age = days - 1 - i
        d = (end - timedelta(days=age)).date().isoformat()
        # Progress 0→1 from oldest to newest
        t = i / max(days - 1, 1)
        # Base: unwind med drift so today lands near current price
        scale = 1.0 - daily_drift * age
        # Mild sine wobble keyed by seed
        wobble = 1.0 + 0.025 * math.sin((seed * 1.7 + i * 0.35)) * (0.4 + 0.6 * t)
        # Slight extra lift in last week from short move
        if age < 7:
            scale *= 1.0 - recent_bias * (7 - age) / 7.0 * 0.5
        jp_price = round(price_hkd * scale * wobble, 2)
        if hk_ask_hkd is not None:
            spread_ratio = hk_ask_hkd / price_hkd if price_hkd else 1.0
            ask = round(jp_price * spread_ratio * (1.0 + 0.01 * math.sin(seed + i * 0.2)), 2)
        else:
            ask = None
        # Volume: mean around vol_7d, spike toward today if elevated
        base_vol = vol_7d * (0.75 + 0.5 * (0.5 + 0.5 * math.sin(seed * 0.9 + i * 0.41)))
        if age == 0:
            vol = float(vol_today)
        elif age < 3 and vol_today > vol_7d:
            vol = round(vol_7d + (vol_today - vol_7d) * (1 - age / 3), 1)
        else:
            vol = round(base_vol, 1)
        points.append(
            {
                "date": d,
                "price_hkd": jp_price,
                "hk_ask_hkd": ask,
                "volume": vol,
            }
        )
    # Force last point to match current snapshot exactly
    points[-1]["price_hkd"] = price_hkd
    points[-1]["hk_ask_hkd"] = hk_ask_hkd
    points[-1]["volume"] = float(vol_today)
    return points


def generate_sample_items(cfg: dict, now: datetime) -> list[dict]:
    """Fake but realistic JP PSA10 + sealed examples for UI wiring.
    Marked is_sample=True / 範例資料 in meta.
    """
    fx = cfg["fx_jpy_to_hkd"]
    hist_days = int(cfg.get("history_days", 90))
    # name_zh, name_jp, kind, set, jpy_price, jpy_prev_short, jpy_prev_med,
    # vol_today, vol_7d_avg, hk_ask_jpy_equiv (or None), liquidity_score
    seeds = [
        (
            "皮卡丘 ex SAR PSA10",
            "ピカチュウex SAR PSA10",
            "psa10",
            "sv2a / 198/165",
            185000,
            172000,
            155000,
            42,
            22,
            210000,
            96,
        ),
        (
            "噴火龍 ex SAR PSA10",
            "リザードンex SAR PSA10",
            "psa10",
            "sv2a / 201/165",
            98000,
            101000,
            110000,
            28,
            30,
            105000,
            88,
        ),
        (
            "151 補充包 BOX（未開封）",
            "ポケモンカード151 BOX 未開封",
            "sealed",
            "SV2a",
            42000,
            38500,
            36000,
            65,
            40,
            48000,
            94,
        ),
        (
            "黑炎支配者 BOX（未開封）",
            "黒炎の支配者 BOX 未開封",
            "sealed",
            "SV3",
            18500,
            19000,
            21000,
            18,
            25,
            22000,
            72,
        ),
        (
            "月亮伊布 VMAX HR PSA10",
            "ブラッキーVMAX HR PSA10",
            "psa10",
            "S6a / 095/069",
            320000,
            295000,
            280000,
            9,
            5,
            350000,
            61,
        ),
        (
            "未來閃光 BOX（未開封）",
            "未来の一閃 BOX 未開封",
            "sealed",
            "SV4M",
            9800,
            10200,
            11500,
            55,
            48,
            12800,
            85,
        ),
        (
            "耿鬼 ex SAR PSA10",
            "ゲンガーex SAR PSA10",
            "psa10",
            "sv5a / 099/071",
            45000,
            44800,
            44000,
            14,
            16,
            52000,
            70,
        ),
        (
            "古代咆哮 BOX（未開封）",
            "古代の咆哮 BOX 未開封",
            "sealed",
            "SV4K",
            11200,
            10800,
            12000,
            33,
            20,
            None,
            68,
        ),
    ]

    items = []
    for i, row in enumerate(seeds):
        (
            name_zh,
            name_jp,
            kind,
            set_code,
            price_jpy,
            prev_s,
            prev_m,
            vol,
            vol7,
            hk_jpy,
            liq,
        ) = row
        price = hkd(price_jpy, fx)
        short_pct = round((price_jpy - prev_s) / prev_s * 100, 2)
        med_pct = round((price_jpy - prev_m) / prev_m * 100, 2)
        vol_ratio = round(vol / vol7, 2) if vol7 else 0.0
        hk_hkd = hkd(hk_jpy, fx) if hk_jpy is not None else None
        spread_pct = (
            round((hk_hkd - price) / price * 100, 2) if hk_hkd is not None else None
        )
        sid = f"sample-{i+1:03d}"
        history = generate_history(
            days=hist_days,
            end=now,
            price_hkd=price,
            hk_ask_hkd=hk_hkd,
            short_pct=short_pct,
            med_pct=med_pct,
            vol_today=vol,
            vol_7d=float(vol7),
            seed=i + 1,
        )
        items.append(
            {
                "id": sid,
                "name_zh": name_zh,
                "name_jp": name_jp,
                "kind": kind,
                "set": set_code,
                "image": f"images/{sid}.webp",
                "price_hkd": price,
                "price_jpy": price_jpy,
                "short_change_pct": short_pct,
                "medium_change_pct": med_pct,
                "volume_today": vol,
                "volume_7d_avg": vol7,
                "volume_ratio": vol_ratio,
                "liquidity_score": liq,
                "hk_ask_hkd": hk_hkd,
                "spread_jp_hk_pct": spread_pct,
                "sources": ["yahoo_auctions_jp", "snkrdunk"],
                "is_sample": True,
                "hk_listings_n": 1 if hk_hkd is not None else 0,
                "history": history,
            }
        )
        attach_public_quotes(
            items[-1],
            watch={"search_jp": name_jp, "search_hk": name_zh, "kind": kind},
            lowest_hkd=hk_hkd,
            bid_hkd=None,
        )
    return items


def compute_sections(items: list[dict], cfg: dict) -> dict:
    th = cfg["thresholds"]
    short_t = th["short_move_pct"]
    med_t = th["medium_move_pct"]
    vol_t = th["volume_vs_7d_avg"]

    big_moves = []
    for it in items:
        reasons = []
        if abs(it["short_change_pct"]) >= short_t:
            reasons.append(f"1日 {it['short_change_pct']:+.1f}%")
        if abs(it["medium_change_pct"]) >= med_t:
            reasons.append(f"7日 {it['medium_change_pct']:+.1f}%")
        if it["volume_ratio"] >= vol_t:
            reasons.append(f"量能 {it['volume_ratio']:.1f}×7日均")
        if reasons:
            # sections keep full item incl. history for click-through
            big_moves.append({**it, "move_reasons": reasons})

    big_moves.sort(
        key=lambda x: max(abs(x["short_change_pct"]), abs(x["medium_change_pct"])),
        reverse=True,
    )

    liquidity = sorted(items, key=lambda x: x["liquidity_score"], reverse=True)
    liquidity = liquidity[: cfg["top_n"]]

    spreads = [
        it
        for it in items
        if it.get("spread_jp_hk_pct") is not None
    ]
    spreads.sort(key=lambda x: abs(x["spread_jp_hk_pct"]), reverse=True)

    def without_history(it: dict) -> dict:
        """Sections omit history to keep latest.json lean; items[] + series files hold it."""
        return {k: v for k, v in it.items() if k != "history"}

    return {
        "big_moves": [without_history(it) for it in big_moves],
        "liquidity": [without_history(it) for it in liquidity],
        "spreads": [without_history(it) for it in spreads],
    }


def build_payload(cfg: dict) -> dict:
    now = datetime.now(HK_TZ)
    items = generate_sample_items(cfg, now)
    sections = compute_sections(items, cfg)
    return {
        "meta": {
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Hong_Kong",
            "is_sample": True,
            "sample_label": "範例資料 — 非正式行情，僅供 UI / pipeline 測試",
            "fx_jpy_to_hkd": cfg["fx_jpy_to_hkd"],
            "display_currency": cfg["display_currency"],
            "thresholds": cfg["thresholds"],
            "top_n": cfg["top_n"],
            "history_days": cfg["history_days"],
            "item_count": len(items),
            "pipeline": [
                "fetch (stub: sample)",
                "normalize HKD",
                "compute movers / liquidity / spreads",
                "write latest.json + history day file + series",
            ],
            "sources_enabled": {
                k: bool(v.get("enabled", False))
                for k, v in (cfg.get("sources") or {}).items()
                if k in ("yahoo_auctions_jp", "snkrdunk")
            },
        },
        "items": items,
        "sections": {
            "大異動": sections["big_moves"],
            "流動性": sections["liquidity"],
            "價差": sections["spreads"],
        },
    }


def write_series_files(items: list[dict], meta: dict) -> int:
    """Write per-item ~90d series under data/history/series/{id}.json."""
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for it in items:
        doc = {
            "id": it["id"],
            "name_zh": it["name_zh"],
            "name_jp": it.get("name_jp"),
            "kind": it["kind"],
            "set": it.get("set"),
            "is_sample": True,
            "sample_note": "範例歷史序列 — 非正式行情",
            "history_days": len(it.get("history") or []),
            "updated_at": meta.get("updated_at"),
            "history": it.get("history") or [],
        }
        path = SERIES_DIR / f"{it['id']}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        written += 1
    return written


def write_outputs(payload: dict) -> None:
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    with LATEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # History: one file per calendar day (HK); slim copy for format docs
    day = payload["meta"]["updated_at"][:10]
    history_doc = {
        "date": day,
        "note": "每日快照格式：同 latest.json 精簡版（meta + items）。保留約 history_days 天。",
        "meta": {
            "updated_at": payload["meta"]["updated_at"],
            "fx_jpy_to_hkd": payload["meta"]["fx_jpy_to_hkd"],
            "is_sample": payload["meta"]["is_sample"],
            "item_count": payload["meta"]["item_count"],
        },
        "items": [
            {
                "id": it["id"],
                "name_zh": it["name_zh"],
                "kind": it["kind"],
                "price_hkd": it["price_hkd"],
                "price_jpy": it["price_jpy"],
                "volume_today": it["volume_today"],
                "liquidity_score": it["liquidity_score"],
                "hk_ask_hkd": it.get("hk_ask_hkd"),
                "hk_ask_low_hkd": it.get("hk_ask_low_hkd"),
                "hk_bid_hkd": it.get("hk_bid_hkd"),
            }
            for it in payload["items"]
        ],
    }
    hist_path = HISTORY_DIR / f"{day}.json"
    with hist_path.open("w", encoding="utf-8") as f:
        json.dump(history_doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_series = write_series_files(payload["items"], payload["meta"])

    print(f"Wrote {LATEST_PATH.relative_to(ROOT)}")
    print(f"Wrote {hist_path.relative_to(ROOT)}")
    print(f"Wrote {n_series} series under data/history/series/")
    print(
        f"Sample items={payload['meta']['item_count']} | "
        f"大異動={len(payload['sections']['大異動'])} | "
        f"流動性={len(payload['sections']['流動性'])} | "
        f"價差={len(payload['sections']['價差'])} | "
        f"history_days={payload['meta']['history_days']}"
    )


def main() -> None:
    cfg = load_config()
    payload = build_payload(cfg)
    write_outputs(payload)


if __name__ == "__main__":
    main()
