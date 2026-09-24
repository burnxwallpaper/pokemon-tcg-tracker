"""Title match for Yahoo Auctions JP closed/sold comps.

Yahoo's `p=` search WAND-expands once a query picks up a set name or a
card number, so the raw page mixes other PSA10s. Callers must refuse a
WAND page. This module then keeps only the slab or sealed SKU asked for.
No match → no price.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ._http import median

JST = timezone(timedelta(hours=9))

# Longer phrases first. These are discriminators, not the product itself.
_SET_PHRASES: tuple[str, ...] = (
    "シャイニートレジャー",
    "VSTARユニバース",
    "ロストアビス",
    "クレイバースト",
    "テラスタルフェス",
    "超電ブレイカー",
    "黒炎の支配者",
    "ポケモンカード151",
    "スカーレットex",
    "バイオレットex",
    "メガドリーム",
    "イーブイヒーローズ",
)

# Longest first so ミュウツー is claimed before ミュウ.
_CARD_STEMS: tuple[str, ...] = tuple(
    sorted(
        (
            "ゴッホピカチュウ",
            "イーブイヒーローズ",
            "コライドン",
            "ミライドン",
            "ピカチュウ",
            "リザードン",
            "ゲンガー",
            "ナンジャモ",
            "ゲッコウガ",
            "ミュウツー",
            "ミュウ",
            "ブラッキー",
            "リーフィア",
            "イーブイ",
            "ギラティナ",
            "サーナイト",
            "ルカリオ",
            "ルギア",
            "エリカ",
            "ミモザ",
            "セレナ",
            "アセロラ",
            "シロナ",
            "ルチア",
            "ゼイユ",
            "ホウオウ",
            "レックウザ",
            "カメックス",
        ),
        key=len,
        reverse=True,
    )
)

_SEALED_STEMS: tuple[str, ...] = tuple(
    sorted(
        (
            "ポケモンカード151",
            "シャイニートレジャー",
            "テラスタルフェス",
            "ストームエメラルダ",
            "ニンジャスピナー",
            "メガシンフォニア",
            "バトルパートナーズ",
            "ロケット団の栄光",
            "黒炎の支配者",
            "ブラックボルト",
            "ホワイトフレア",
            "ステラミラクル",
            "古代の咆哮",
            "メガドリーム",
            "メガブレイブ",
            "ムニキスゼロ",
            "インフェルノx",
            "アビスアイ",
        ),
        key=len,
        reverse=True,
    )
)

_FRACTION = re.compile(r"(\d{2,3})\s*[/／]\s*(\d{2,3})")
_SET_CODE = re.compile(r"(?<![a-z0-9])((?:sv|s|m)\d+[a-z]?|svp)(?![a-z0-9])", re.I)
_RARITY = ("csr", "chr", "sar", "sr", "ur", "hr", "sa", "ar")


def is_fuzzy_closedsearch(total: int, wand: str | None) -> bool:
    """True when Yahoo expanded the query instead of AND-matching it."""
    if wand and "WAND" in wand:
        return True
    return int(total or 0) >= 8000


def auction_url(auction_id: str | None) -> str | None:
    if not auction_id:
        return None
    return f"https://auctions.yahoo.co.jp/jp/auction/{auction_id}"


def _norm(text: str) -> str:
    s = text.lower()
    s = s.translate(str.maketrans("ＰＳＡ０１２３４５６７８９ｘ×＆＋／", "psa0123456789xx&+/"))
    s = s.replace("　", "").replace(" ", "")
    s = s.replace("エク", "ex")
    return s


def _kind(item: dict) -> str:
    return str(item.get("kind") or "psa10")


def _fraction(text: str) -> tuple[str, str] | None:
    found = _FRACTION.findall(text or "")
    if not found:
        return None
    left, right = found[0]
    return left, right


def _fractions(text: str) -> list[tuple[str, str]]:
    return [(a, b) for a, b in _FRACTION.findall(text or "")]


def _item_fraction(item: dict) -> tuple[str, str] | None:
    """Printed card number. A set code like S11 / 125 is not 11/125."""
    text = f"{item.get('set') or ''} {item.get('search_jp') or ''}"
    text = re.sub(r"(?i)(?<![a-z0-9])(?:sv|s|m)\d+[a-z]?\s*/", " ", text)
    return _fraction(text)


def _item_set_code(item: dict) -> str | None:
    raw = str(item.get("set") or "").strip().lower()
    m = re.match(r"([a-z]+\d+[a-z]?)", raw)
    if not m:
        return None
    return m.group(1)


def extra_set_phrase(item: dict) -> str | None:
    """Set nickname that is not the product name itself."""
    name = str(item.get("name_jp") or "")
    search = str(item.get("search_jp") or "")
    blob = f"{name} {search}"
    for phrase in _SET_PHRASES:
        if phrase not in blob:
            continue
        rest = _norm(name.replace(phrase, ""))
        rest = re.sub(r"psa10|sar|sr|ur|hr|sa|box|未開封|シュリンク", "", rest)
        rest = rest.replace("ex", "")
        if len(rest) >= 2:
            return phrase
    return None


def build_queries(item: dict) -> list[str]:
    """Exact-first queries. Quoted set name, then the short name if WAND fires."""
    kind = _kind(item)
    name = str(item.get("name_jp") or item.get("search_jp") or "").strip()
    if kind == "sealed":
        return [name] if name else []

    phrase = extra_set_phrase(item)
    base = name
    if phrase:
        base = re.sub(re.escape(phrase), " ", name)
    base = re.sub(r"\s+", " ", base).strip()
    if "psa" not in base.lower():
        base = f"{base} PSA10".strip()
    minus = " -連番"
    if "メガ" not in name and "mega" not in name.lower():
        minus = " -メガ -連番"
    queries: list[str] = []
    frac = _item_fraction(item)
    if frac:
        queries.append(f'{base} "{frac[0]}/{frac[1]}"{minus}')
    if phrase:
        queries.append(f'{base} "{phrase}"{minus}')
    queries.append(f"{base}{minus}")
    out: list[str] = []
    for query in queries:
        cleaned = re.sub(r"\s+", " ", query).strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _rarity_text(text: str) -> str:
    s = text.lower()
    s = s.translate(str.maketrans("ＰＳＡ０１２３４５６７８９", "psa0123456789"))
    s = re.sub(r"psa\s*\d*", " ", s)
    return re.sub(r"[^a-z]+", " ", s)


def _rarities(text: str) -> set[str]:
    """Grade tokens. Spaces are kept so SAR PSA10 is still SAR, not sarpsa."""
    s = _rarity_text(text)
    found: set[str] = set()
    for rarity in _RARITY:
        if re.search(rf"(?<![a-z]){rarity}(?![a-z])", s):
            found.add(rarity)
    return found


def _rarity(text: str) -> str | None:
    found = _rarities(text)
    for rarity in _RARITY:
        if rarity in found:
            return rarity
    return None


def _is_psa10(title: str) -> bool:
    n = _norm(title)
    if any(bit in n for bit in ("狙い", "候補", "期待", "目標", "取れる", "提出", "相当")):
        return False
    if any(bit in n for bit in ("gemix", "ジェム", "cgc", "bgsのみ")):
        return False
    if not re.search(r"psa10", n):
        return False
    if re.search(r"psa[1-9](?!\d)", n):
        return False
    companies = 0
    for bit in ("psa", "bgs", "cgc", "ars"):
        if bit in n:
            companies += 1
    if companies >= 2:
        return False
    return True


def _is_lot(title: str) -> bool:
    n = _norm(title)
    if any(bit in n for bit in ("連番", "まとめ", "大量", "福袋", "オリパ", "コンプリート", "コンプ", "引退", "おまけ")):
        return True
    if "&" in n or "+" in n:
        return True
    if re.search(r"[2-9]枚", n):
        return True
    if re.search(r"全\d+枚", n):
        return True
    return False


def _stems_in(title_n: str) -> list[str]:
    remaining = title_n
    found: list[str] = []
    for stem in _CARD_STEMS:
        stem_n = _norm(stem)
        if stem_n and stem_n in remaining:
            found.append(stem_n)
            remaining = remaining.replace(stem_n, " ")
    return found


def _identity(item: dict) -> str:
    name = str(item.get("name_jp") or "")
    phrase = extra_set_phrase(item) or ""
    if phrase:
        name = name.replace(phrase, "")
    name = re.sub(r"PSA\s*10", "", name, flags=re.I)
    name = re.sub(r"\b(SAR|SR|UR|HR|SA|CSR|CHR|AR)\b", "", name, flags=re.I)
    name = name.replace("未開封", "").replace("シュリンク", "")
    name = re.sub(r"\bBOX\b", "", name, flags=re.I)
    return _norm(name)


def _evolution_ok(identity: str, title_n: str) -> bool:
    # "V SR" / "V SA" collapse to vsr / vsa once spaces are removed.
    title_n = re.sub(r"v(?=(?:csr|chr|sar|sr|ur|hr|sa|ar))", "v ", title_n)
    identity = re.sub(r"v(?=(?:csr|chr|sar|sr|ur|hr|sa|ar))", "v ", identity)
    if "vstar" in identity:
        return "vstar" in title_n
    if "vmax" in identity:
        return "vmax" in title_n
    wants_v = re.search(r"v(?![a-z])", identity) is not None
    has_v = re.search(r"v(?![a-z])", title_n) is not None
    if wants_v:
        return has_v and "vstar" not in title_n and "vmax" not in title_n
    if "vstar" in title_n or "vmax" in title_n:
        return False
    return True


def _set_codes(text: str) -> set[str]:
    return {m.group(1).lower() for m in _SET_CODE.finditer(_norm(text))}


def _allowed_phrases(item: dict) -> set[str]:
    """Set nicknames that may appear on this SKU's title."""
    allowed: set[str] = set()
    phrase = extra_set_phrase(item)
    if phrase:
        allowed.add(phrase)
    code = _item_set_code(item)
    frac = _item_fraction(item)
    if code == "sv2a" or (frac is not None and frac[1] == "165"):
        allowed.add("ポケモンカード151")
    return allowed


def _phrase_hits(title_n: str) -> set[str]:
    hits: set[str] = set()
    for phrase in _SET_PHRASES:
        if _norm(phrase) in title_n:
            hits.add(phrase)
    if re.search(r"(?<![0-9])151(?![0-9])", title_n):
        hits.add("ポケモンカード151")
    return hits


def _psa_title_ok(title: str, item: dict) -> bool:
    if not _is_psa10(title) or _is_lot(title):
        return False
    title_n = _norm(title)
    identity = _identity(item)
    if len(identity) <= 2:
        if not re.search(r"(?<![a-z0-9])n(?![a-z0-9])", title_n):
            return False
        if "ポケモン" not in title and "ポケカ" not in title:
            return False
        # 「Nのゾロアーク」 is a different card from the trainer N.
        if "nの" in title_n and "の" not in identity:
            return False
    elif identity not in title_n:
        return False
    if "メガ" not in identity and "mega" not in identity:
        if "メガ" in title_n or "mega" in title_n:
            return False
    if "ex" in identity and "ex" not in title_n:
        return False
    if not _evolution_ok(identity, title_n):
        return False
    item_r = _rarity(str(item.get("name_jp") or "") + str(item.get("search_jp") or ""))
    # SA slabs are often titled "SR SA". Keep the asked grade if it is present.
    if item_r and item_r not in _rarities(title):
        return False
    if "プロモ" in title and "プロモ" not in str(item.get("name_jp") or "") and "svp" not in str(item.get("set") or "").lower():
        return False
    stems = _stems_in(title_n)
    own = [stem for stem in stems if stem in identity or identity in stem]
    if stems and not own:
        return False
    if any(stem not in identity and identity not in stem for stem in stems):
        return False
    want = _item_fraction(item)
    got = _fractions(title)
    if want:
        if want not in got:
            return False
    elif got:
        local = re.search(r"/\s*(\d{2,3})\s*$", str(item.get("set") or "").strip())
        if local and all(num != local.group(1) for num, _den in got):
            return False
    phrase = extra_set_phrase(item)
    hits = _phrase_hits(title_n)
    code = _item_set_code(item)
    title_codes = _set_codes(title)
    if phrase and phrase not in hits and (not code or code not in title_codes):
        return False
    allowed = _allowed_phrases(item)
    if any(hit not in allowed for hit in hits):
        return False
    if code and any(c != code for c in title_codes):
        return False
    return True


def _sealed_title_ok(title: str, item: dict) -> bool:
    title_n = _norm(title)
    if any(bit in title_n for bit in ("サーチ済", "シュリンクなし", "開封済")):
        return False
    if "未開封" not in title and "シュリンク" not in title:
        return False
    if "box" not in title_n and "ボックス" not in title and "箱" not in title_n:
        return False
    if re.search(r"[2-9]\s*(?:box|ボックス|箱)", title, re.I):
        return False
    if re.search(r"(?:未開封|シュリンク付き)\s*[2-9]\s*$", title):
        return False
    if re.search(r"\d+\s*パック", title):
        return False
    if "box分" in title_n or "ボックス分" in title:
        return False
    if re.search(r"(?:box|ボックス)\s*[x×*]\s*[2-9]", title, re.I):
        return False
    if "各1" in title or "各１" in title:
        return False
    if any(bit in title for bit in ("点セット", "まとめ", "大量", "カートン", "デッキビルド", "カードファイル", "おまけ")):
        return False
    if re.search(r"計\s*[2-9]\s*点", title) or re.search(r"[2-9]\s*個", title):
        return False
    if "シュリンク無" in title or "シュリンクなし" in title:
        return False
    if any(bit in title for bit in ("シュリンク破れ", "箱凹み", "箱傷")):
        return False
    if re.search(r"(?<![a-z])ケース(?![a-z])", title) or re.search(r"(?<![a-z])case(?![a-z])", title_n):
        return False
    if re.search(r"(?<![a-z])dx(?![a-z])", title_n) and "dx" not in _norm(str(item.get("name_jp") or "")):
        return False
    if any(bit in title_n for bit in ("英語", "英語版", "english", "海外版")):
        return False
    identity = _identity(item)
    if not identity or identity not in title_n:
        # 151 listings often drop ポケモンカード and keep 151 + BOX.
        if identity != _norm("ポケモンカード151") or "151" not in title_n:
            return False
    present = [stem for stem in _SEALED_STEMS if _norm(stem) in title_n]
    for stem in present:
        stem_n = _norm(stem)
        if stem_n == identity or stem_n in identity or identity in stem_n:
            continue
        return False
    return True


def title_matches(title: str, item: dict) -> bool:
    if not title or not str(title).strip():
        return False
    if _kind(item) == "sealed":
        return _sealed_title_ok(title, item)
    if _kind(item) == "psa10":
        return _psa_title_ok(title, item)
    return False


def _price_ok(price: int, item: dict) -> bool:
    if _kind(item) == "sealed":
        return 3000 <= price <= 160_000
    return 2000 <= price <= 1_500_000


def filter_comps(comps: list[dict], item: dict) -> list[dict]:
    """Keep sold comps whose title is this SKU. Unsold (0 bids) dropped."""
    kept: list[dict] = []
    for comp in comps:
        title = str(comp.get("title") or "")
        if not title_matches(title, item):
            continue
        try:
            price = int(comp.get("price_jpy"))
        except (TypeError, ValueError):
            continue
        if not _price_ok(price, item):
            continue
        bids = comp.get("bid_count")
        if bids is not None:
            try:
                if int(bids) < 1:
                    continue
            except (TypeError, ValueError):
                continue
        kept.append(comp)
    return kept


def _end_dt(comp: dict) -> datetime | None:
    raw = comp.get("end_time")
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt


def robust_median_jpy(prices: list[int]) -> int | None:
    """Median after dropping far outliers. Scattered markets return None."""
    vals = sorted(int(p) for p in prices if isinstance(p, int) and p > 0)
    if not vals:
        return None
    if len(vals) >= 4:
        mid = median(vals)
        if mid is None:
            return None
        kept = [p for p in vals if (mid / 3) <= p <= (mid * 3)]
        if len(kept) < 2:
            return None
        vals = kept
    if len(vals) == 1:
        return vals[0]
    mid = median(vals)
    if mid is None:
        return None
    return int(round(mid))


def quote_comps(
    comps: list[dict],
    *,
    now: datetime | None = None,
) -> tuple[int | None, list[dict]]:
    """Recent-window robust median and the comps that produced it.

    Prefer the last 21 days when there are at least 3 comps, else 45 days,
    else any matched sale. Outliers are removed before the median.
    """
    if not comps:
        return None, []
    now = now or datetime.now(JST)
    dated: list[tuple[datetime | None, dict]] = [(_end_dt(c), c) for c in comps]

    def within(days: int) -> list[dict]:
        cutoff = now - timedelta(days=days)
        return [c for dt, c in dated if dt is not None and dt >= cutoff]

    chosen = within(21)
    if len(chosen) < 3:
        wider = within(45)
        if len(wider) >= 2:
            chosen = wider
        elif chosen:
            pass
        else:
            chosen = [c for _dt, c in dated]
    if not chosen:
        return None, []
    prices = [int(c["price_jpy"]) for c in chosen]
    mid = robust_median_jpy(prices)
    if mid is None:
        return None, []
    if len(prices) >= 4:
        center = median(prices)
        if center:
            chosen = [
                c
                for c in chosen
                if (center / 3) <= int(c["price_jpy"]) <= (center * 3)
            ]
    chosen.sort(key=lambda c: _end_dt(c) or datetime.min.replace(tzinfo=JST), reverse=True)
    return mid, chosen


def debug_from_comps(comps: list[dict], *, query: str, limit: int = 8) -> dict[str, Any]:
    """Per-item audit. Always includes up to `limit` comps (at least 3 when present)."""
    rows = comps[: max(limit, 3)] if len(comps) > 3 else comps
    titles: list[str] = []
    prices: list[int] = []
    urls: list[str] = []
    for comp in rows:
        titles.append(str(comp.get("title") or ""))
        prices.append(int(comp["price_jpy"]))
        url = auction_url(str(comp.get("auction_id") or "") or None)
        if url:
            urls.append(url)
    return {
        "query": query,
        "matched_titles": titles,
        "matched_prices_jpy": prices,
        "source_urls": urls,
        "matched_n": len(comps),
    }
