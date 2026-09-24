"""Title matching for HK asks. Shared by Carousell, HKCardLink, and shops."""
from __future__ import annotations

import re
from typing import Any

from ._http import median

# Character / product names. Longer terms shadow shorter ones (伊布 vs 月亮伊布).
_GROUPS: list[dict[str, Any]] = [
    {"id": "koraidon", "terms": ["故勒頓", "koraidon", "コライドン"]},
    {"id": "miraidon", "terms": ["密勒頓", "miraidon", "ミライドン"]},
    {"id": "pikachu", "terms": ["皮卡丘", "pikachu", "ピカチュウ", "比卡超"]},
    {"id": "charizard", "terms": ["噴火龍", "charizard", "リザードン", "喷火龙"]},
    {"id": "gengar", "terms": ["耿鬼", "gengar", "ゲンガー"]},
    {"id": "iono", "terms": ["奇樹", "iono", "ナンジャモ", "奇树"]},
    {"id": "greninja", "terms": ["甲賀忍蛙", "greninja", "ゲッコウガ"]},
    {"id": "mewtwo", "terms": ["火箭隊超夢", "超夢", "mewtwo", "ミュウツー"]},
    {"id": "mew", "terms": ["夢幻", "mew", "ミュウ"], "excludes": ["mewtwo", "ミュウツー", "超夢"]},
    {"id": "umbreon", "terms": ["月亮伊布", "umbreon", "ブラッキー"]},
    {"id": "leafeon", "terms": ["葉伊布", "leafeon", "リーフィア"]},
    {"id": "eevee", "terms": ["伊布", "eevee", "イーブイ"], "excludes": [
        "umbreon", "leafeon", "sylveon", "glaceon", "espeon", "flareon", "vaporeon", "jolteon",
        "月亮伊布", "葉伊布", "ブラッキー", "リーフィア", "ニンフィア", "グレイシア",
    ]},
    {"id": "giratina", "terms": ["騎拉帝納", "giratina", "ギラティナ"]},
    {"id": "gardevoir", "terms": ["沙奈朵", "gardevoir", "サーナイト"]},
    {"id": "lucario", "terms": ["路卡利歐", "lucario", "ルカリオ"]},
    {"id": "lugia", "terms": ["洛奇亞", "lugia", "ルギア"]},
    {"id": "erika", "terms": ["莉佳的邀請", "莉佳", "erika", "エリカ"]},
    {"id": "miriam", "terms": ["米莫莎", "miriam", "ミモザ"]},
    {"id": "serena", "terms": ["莎莉娜", "serena", "セレナ"]},
    {"id": "acerola", "terms": ["阿塞蘿拉", "acerola", "アセロラ"]},
    {"id": "cynthia", "terms": ["竹蘭的霸氣", "竹蘭", "cynthia", "シロナ"]},
    {"id": "lisia", "terms": ["露琪亞", "lisia", "ルチア"]},
    {"id": "carmine", "terms": ["丹瑜", "carmine", "ゼイユ"]},
    {"id": "hooh", "terms": ["阿響的鳳王", "鳳王", "ホウオウ", "hooh", "ho-oh"]},
    {"id": "nsar", "terms": ["nsar", "エヌ"]},
    {"id": "abyss", "terms": ["深淵之眼", "abysseye", "アビスアイ", "abyss eye"]},
    {"id": "storm", "terms": ["風暴翡翠", "stormemeralda", "stormemerald", "ストームエメラルダ", "storm emeralda"]},
    {"id": "dream", "terms": ["超級夢想", "megadream", "メガドリーム", "mega dream"]},
    {"id": "ninja", "terms": ["忍者陀螺", "忍者飛旋", "ninjaspinner", "ニンジャスピナー", "ninja spinner"]},
    {"id": "inferno", "terms": ["烈焰x", "烈焰", "インフェルノ", "inferno"]},
    {"id": "brave", "terms": ["超級勇氣", "megabrave", "メガブレイブ", "mega brave"]},
    {"id": "symphonia", "terms": ["超級協奏", "megasymphonia", "megasiphonia", "メガシンフォニア", "mega symphonia", "mega siphonia"]},
    {"id": "munikis", "terms": ["尼比斯零", "尼比斯", "虛無歸零", "munikis", "ムニキスゼロ", "munikis zero"]},
    {"id": "fest", "terms": ["太晶慶典", "terastalfestival", "テラスタルフェス", "terastal festival"]},
    {"id": "shinybox", "terms": ["閃色寶藏", "shinytreasure", "シャイニートレジャー", "shiny treasure"]},
    {"id": "battle", "terms": ["對戰夥伴", "battlepartners", "バトルパートナーズ", "battle partners"]},
    {"id": "stellar", "terms": ["星晶奇跡", "stellarmiracle", "ステラミラクル", "stellar miracle"]},
    {"id": "glory", "terms": ["火箭隊的榮耀", "ロケット団の栄光", "gloryoftheteamrocket"]},
    {"id": "bolt", "terms": ["黑雷", "blackbolt", "ブラックボルト", "black bolt"]},
    {"id": "flare", "terms": ["白炎", "whiteflare", "ホワイトフレア", "white flare"]},
    {"id": "ancient", "terms": ["古代咆哮", "ancientroar", "古代の咆哮", "ancient roar"]},
    {"id": "blackflame", "terms": ["黑炎支配者", "黑炎的支配者", "黒炎の支配者", "黑炎", "黒炎", "black flame", "obsidian flames"]},
    {"id": "heroes", "terms": ["伊布英雄", "イーブイヒーローズ", "eeveeheroes", "eevee heroes"]},
    {"id": "sv151", "terms": ["ポケモンカード151", "pokemoncard151", "pokemon 151", "sv2a"]},
]

# Disambiguators. Exclusive ones must not appear on a title unless the query has them.
_MARKERS: list[dict[str, Any]] = [
    {"id": "mega", "exclusive": True, "needles": ["超級", "mega", "メガ"]},
    {"id": "shiny", "exclusive": True, "needles": ["閃色寶藏", "シャイニートレジャー", "shiny treasure", "sv4a", "閃"]},
    {"id": "sv151", "exclusive": True, "needles": ["151", "sv2a"]},
    {"id": "obsidian", "exclusive": True, "needles": ["黑炎", "黒炎", "blackflame", "obsidian", "sv3"]},
    {"id": "electric", "exclusive": True, "needles": ["超電", "superelectric", "super electric"]},
    {"id": "heroes", "exclusive": True, "needles": ["伊布英雄", "イーブイヒーローズ", "eevee heroes", "eeveeheroes"]},
    {"id": "vstar", "exclusive": False, "needles": ["vstar"]},
]

_NON_JP = (
    "繁中", "繁體", "繁体", "中文版", "港版", "台版", "台灣版", "简中", "簡中",
    "韓版", "korean", "英文版", "(cn)", "(hk)", "(tw)", "(kr)",
)
_JP_OK = ("日版", "日文", "japanese", "(jp)", "日本", " jp")

_LOT = ("十連", "連號", "sequential", "set of", "lot of", "一套")
_JUNK = ("福袋", "oripa", "抽池", "刮卡", "mezastar", "明耀之星", "plamo", "組裝模型", "退坑", "禮盒", "礼盒")


def _item_blob(item: dict) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("search_hk", "name_zh", "name_jp", "set", "tcgdex_id", "search_jp")
    )


def _norm(s: str) -> str:
    s = s.lower().replace("ｘ", "x").replace("×", "x")
    s = s.replace("　", " ")
    s = re.sub(r"psa\s*10(?:\.0)?", "psa10", s)
    s = re.sub(r"[\s\-_/.,，、|#\[\]（）()【】'’]+", "", s)
    return s


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def _needle_in(text_n: str, needle: str) -> bool:
    needle_n = _norm(needle)
    if not needle_n:
        return False
    if needle_n == "sv3":
        return re.search(r"sv3(?![a-z])", text_n) is not None
    return needle_n in text_n


def _marker_ids(text: str) -> set[str]:
    n = _norm(text)
    found: set[str] = set()
    for marker in _MARKERS:
        if any(_needle_in(n, needle) for needle in marker["needles"]):
            found.add(marker["id"])
    return found


def _groups_in(text: str) -> list[dict[str, Any]]:
    n = _norm(text)
    hit = [g for g in _GROUPS if any(_norm(t) and _norm(t) in n for t in g["terms"])]
    kept: list[dict[str, Any]] = []
    for group in hit:
        shadowed = False
        for other in hit:
            if other is group:
                continue
            for other_term in other["terms"]:
                other_n = _norm(other_term)
                if not other_n or other_n not in n:
                    continue
                for term in group["terms"]:
                    term_n = _norm(term)
                    if term_n and term_n != other_n and term_n in other_n:
                        shadowed = True
        if not shadowed:
            kept.append(group)
    return kept


def _title_hits_group(title_n: str, group: dict[str, Any]) -> bool:
    excludes = [_norm(x) for x in group.get("excludes") or []]
    if any(x and x in title_n for x in excludes):
        return False
    return any(_norm(t) and _norm(t) in title_n for t in group["terms"])


def _wants_charizard_x(text: str) -> bool:
    n = _norm(text)
    return any(s in n for s in ("噴火龍x", "charizardx", "リザードンx"))


def _title_charizard_x_ok(title_n: str, query: str) -> bool:
    if not _wants_charizard_x(query):
        return True
    has_x = any(s in title_n for s in ("噴火龍x", "charizardx", "リザードンx"))
    has_y = any(s in title_n for s in ("噴火龍y", "charizardy", "リザードンy"))
    return has_x and not has_y


def _is_lot(title: str, title_n: str) -> bool:
    low = title.lower()
    if any(bit in low or bit in title_n for bit in _LOT):
        return True
    if title.count("&") >= 1 or title.count("+") >= 1:
        return True
    if len(re.findall(r"\d{2,3}\s*/\s*\d{2,3}", title)) >= 2:
        return True
    return False


def _is_case_or_dx(title: str, query: str) -> bool:
    low = title.lower()
    q = query.lower()
    if any(bit in low for bit in ("卡頓", "carton", "20 boxes", "20 box")):
        return True
    if re.search(r"\bcase\b", low) and not re.search(r"\bcase\b", q):
        return True
    if re.search(r"\bdx\b", low) and not re.search(r"\bdx\b", q):
        return True
    return False


def _non_jp(title: str) -> bool:
    low = title.lower()
    if any(bit in low for bit in _NON_JP) and not any(bit in low for bit in _JP_OK):
        return True
    return False


def _is_psa10(title: str, row: dict | None) -> bool:
    if "psa10" in _norm(title):
        return True
    if not row:
        return False
    company = str(row.get("grade_company") or "").upper()
    try:
        score = float(row["grade_score"]) if row.get("grade_score") is not None else None
    except (TypeError, ValueError):
        score = None
    return company == "PSA" and score is not None and score >= 10


def _is_box(title: str) -> bool:
    low = title.lower()
    return any(bit in low for bit in ("box", "原盒", "未開封", "ボックス", "盒"))


def _has_token(text: str, token: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)", text.lower()) is not None


def _rarity_ok(title: str, query: str) -> bool:
    """Keep SAR/SR/UR/SA from matching a different rarity of the same Pokémon."""
    special = "special art" in title.lower()
    if _has_token(query, "sar") or "special art" in query.lower():
        return _has_token(title, "sar") or special
    if _has_token(query, "sr") and not _has_token(title, "sr"):
        return False
    if _has_token(query, "ur") and not _has_token(title, "ur"):
        return False
    if _has_token(query, "sa") and not (_has_token(title, "sa") or special):
        return False
    return True


def _is_product_not_slab(title: str) -> bool:
    return re.search(r"收藏箱|collection|booster box|elite trainer|補充盒", title, re.I) is not None


_SET_IDS = {
    "abyss", "storm", "dream", "ninja", "inferno", "brave", "symphonia", "munikis",
    "fest", "shinybox", "battle", "stellar", "glory", "bolt", "flare", "ancient",
    "heroes", "blackflame", "sv151",
}

_HINTS = {
    "sv151": "151",
    "obsidian": "黑炎",
    "electric": "超電",
    "shiny": "閃",
    "mega": "Mega",
    "heroes": "英雄",
    "vstar": "VSTAR",
}


def _focus_groups(item: dict) -> list[dict[str, Any]]:
    groups = _groups_in(_item_blob(item))
    set_groups = [g for g in groups if g["id"] in _SET_IDS]
    char_groups = [g for g in groups if g["id"] not in _SET_IDS]
    if item.get("kind") == "sealed" and set_groups:
        return set_groups
    return char_groups or groups


def _label(item: dict) -> str:
    text_n = _norm(_item_blob(item))
    present: list[str] = []
    for group in _focus_groups(item):
        for term in group["terms"]:
            if _has_cjk(term) and _norm(term) in text_n:
                present.append(term)
    label = max(present, key=len) if present else str(item.get("name_zh") or item.get("search_hk") or "")
    label = re.sub(r"PSA\s*10|BOX|未開封|（|）", " ", label, flags=re.I)
    return re.sub(r"\s+", " ", label).strip()


def _hints(item: dict) -> list[str]:
    text = _item_blob(item)
    found = []
    for marker_id in _marker_ids(text):
        hint = _HINTS.get(marker_id)
        if hint:
            found.append(hint)
    if _wants_charizard_x(text):
        found.append("X")
    out: list[str] = []
    for hint in found:
        if hint not in out:
            out.append(hint)
    return out


def primary_query(item: dict) -> str:
    """Specific marketplace query; strict match happens afterwards."""
    label = _label(item)
    extra = " ".join(_hints(item))
    if (item.get("kind") or "psa10") == "sealed":
        return f"{label} {extra} BOX".strip()
    return f"{label} {extra} PSA10".strip()


def extra_queries(item: dict) -> list[str]:
    """Alternate HK spellings when the main search page is noisy."""
    kind = item.get("kind") or "psa10"
    hints = " ".join(_hints(item))
    tail = "BOX" if kind == "sealed" else "PSA10"
    blob = _item_blob(item)
    raw: list[str] = []
    if "皮卡丘" in blob:
        raw.append(f"比卡超 {hints} {tail}")
    if "故勒頓" in blob:
        raw.append("koraidon shiny PSA10")
    if kind == "psa10" and "黑炎" in blob:
        raw.append("噴火龍 SV3 SAR PSA10")
    out: list[str] = []
    for query in raw:
        cleaned = " ".join(query.split())
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def broad_query(item: dict) -> str:
    label = _label(item)
    if (item.get("kind") or "psa10") == "sealed":
        return f"{label} BOX"
    return f"{label} PSA10"


def english_query(item: dict) -> str | None:
    text = _item_blob(item)
    groups = _focus_groups(item)
    ascii_terms: list[str] = []
    for group in groups:
        for term in group["terms"]:
            if term.isascii() and len(_norm(term)) >= 4:
                ascii_terms.append(term)
    if not ascii_terms:
        return None
    label = max(ascii_terms, key=len)
    extra = " ".join(h for h in _hints(item) if h.isascii())
    if (item.get("kind") or "psa10") == "sealed":
        return f"{label} {extra} box".strip()
    return f"{label} {extra} PSA10".strip()


def match_item(rows: list[dict], item: dict) -> list[dict]:
    return match_listings(
        rows,
        keyword=" ".join(
            str(item.get(key) or "") for key in ("search_hk", "set", "tcgdex_id")
        ),
        kind=item.get("kind") or "psa10",
        name_jp=item.get("name_jp"),
        name_zh=item.get("name_zh"),
    )


def match_listings(
    rows: list[dict],
    *,
    keyword: str,
    kind: str,
    name_jp: str | None = None,
    name_zh: str | None = None,
) -> list[dict]:
    query = " ".join(x for x in (keyword, name_jp or "", name_zh or "") if x)
    query_n = _norm(query)
    groups = _groups_in(query)
    if not groups:
        return []
    query_markers = _marker_ids(query)
    hits: list[dict] = []
    for row in rows:
        title = str(row.get("card_name") or row.get("title") or "")
        if not title or _non_jp(title) or _is_lot(title, _norm(title)):
            continue
        if any(bit in title.lower() for bit in _JUNK):
            continue
        title_n = _norm(title)
        if _is_case_or_dx(title, query):
            continue
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if kind == "psa10":
            if (
                not _is_psa10(title, row)
                or _is_product_not_slab(title)
                or not _rarity_ok(title, query)
                or price < 80
                or price > 200_000
            ):
                continue
        elif kind == "sealed":
            if re.search(r"deck build|新手|構築|牌組|原箱", title, re.I):
                continue
            multi = re.search(r"(\d+)\s*盒", title)
            if multi and int(multi.group(1)) >= 2:
                continue
            if not _is_box(title) or price < 80 or price > 25_000:
                continue
        else:
            continue
        if not all(_title_hits_group(title_n, group) for group in groups):
            continue
        query_chars = {g["id"] for g in groups if g["id"] not in _SET_IDS}
        title_chars = [g["id"] for g in _groups_in(title) if g["id"] not in _SET_IDS]
        if any(gid not in query_chars for gid in title_chars):
            continue
        if "m2a" in query_n:
            if "m2a" not in title_n:
                continue
        elif re.search(r"m2(?![a-z])", query_n) and "m2a" in title_n:
            continue
        title_markers = _marker_ids(title)
        if any(marker not in title_markers for marker in query_markers):
            continue
        if any(
            m["exclusive"] and m["id"] in title_markers and m["id"] not in query_markers
            for m in _MARKERS
        ):
            continue
        if not _title_charizard_x_ok(title_n, query):
            continue
        hit = {
            "id": row.get("id"),
            "title": title,
            "price_hkd": price,
            "source": row.get("source"),
        }
        for key in ("url", "listing_type", "created_at", "slug"):
            if row.get(key):
                hit[key] = row.get(key)
        hits.append(hit)
    hits.sort(key=lambda h: h["price_hkd"])
    return hits


def trimmed_asks(prices: list[float]) -> list[float]:
    """Drop far outliers once there are enough asks. Shared by median and lowest."""
    vals = [float(p) for p in prices if p and p > 0]
    if len(vals) >= 4:
        mid = median(vals)
        if mid:
            kept = [p for p in vals if mid / 3 <= p <= mid * 3]
            if kept:
                vals = kept
    return vals


def robust_median(prices: list[float]) -> float | None:
    vals = trimmed_asks(prices)
    if not vals:
        return None
    mid = median(vals)
    if mid is None:
        return None
    return round(mid, 2)


def lowest_ask(prices: list[float]) -> float | None:
    vals = trimmed_asks(prices)
    if not vals:
        return None
    return round(min(vals), 2)
