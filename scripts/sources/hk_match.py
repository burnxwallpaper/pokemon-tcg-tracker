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
    {
        "id": "mewtwo",
        "terms": ["火箭隊超夢", "超夢", "mewtwo", "ミュウツー"],
        "specific": [[
            "火箭隊超夢", "火箭隊的超夢", "team rocket mewtwo", "rocket mewtwo",
            "teamrocketsmewtwo", "rocketsmewtwo", "ロケット団のミュウツー", "ロケット団ミュウツー",
        ]],
    },
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
    {
        "id": "erika",
        "terms": ["莉佳的邀請", "莉佳", "erika", "エリカ"],
        "specific": [["莉佳的邀請", "エリカの招待", "erika's invitation", "招待", "邀請"]],
    },
    {"id": "miriam", "terms": ["米莫莎", "miriam", "ミモザ"]},
    {"id": "serena", "terms": ["莎莉娜", "serena", "セレナ"]},
    {
        "id": "acerola",
        "terms": ["阿塞蘿拉", "acerola", "アセロラ"],
        "specific": [["阿塞蘿拉的預感", "アセロラの予感", "預感", "予感", "premonition"]],
    },
    {
        "id": "cynthia",
        "terms": ["竹蘭的霸氣", "竹蘭", "cynthia", "シロナ"],
        "specific": [["竹蘭的霸氣", "シロナの覇気", "霸氣", "覇気", "ambition"]],
    },
    {
        "id": "lisia",
        "terms": ["露琪亞", "lisia", "ルチア"],
        "specific": [["露琪亞的吸引力", "ルチアのアピール", "吸引力", "アピール", "appeal"]],
    },
    {"id": "carmine", "terms": ["丹瑜", "carmine", "ゼイユ"]},
    {
        "id": "hooh",
        "terms": ["阿響的鳳王", "鳳王", "ホウオウ", "hooh", "ho-oh"],
        "specific": [["阿響的鳳王", "阿響", "ヒビキのホウオウ", "ヒビキ", "ethan"]],
    },
    {"id": "zoroark", "terms": ["索羅亞克", "zoroark", "ゾロアーク"]},
    {"id": "nsar", "terms": ["nsar"]},
    {"id": "abyss", "terms": ["深淵之眼", "abysseye", "アビスアイ", "abyss eye"]},
    {"id": "storm", "terms": ["風暴翡翠", "stormemeralda", "stormemerald", "ストームエメラルダ", "storm emeralda"]},
    {"id": "dream", "terms": ["超級夢想", "megadream", "メガドリーム", "mega dream", "ドリームex", "dream ex"]},
    {"id": "ninja", "terms": ["忍者陀螺", "忍者飛旋", "ninjaspinner", "ニンジャスピナー", "ninja spinner"]},
    {"id": "inferno", "terms": ["烈焰x", "烈焰", "インフェルノ", "inferno"]},
    {"id": "brave", "terms": ["超級勇氣", "megabrave", "メガブレイブ", "mega brave"]},
    {"id": "symphonia", "terms": ["超級協奏", "megasymphonia", "megasiphonia", "メガシンフォニア", "mega symphonia", "mega siphonia"]},
    {"id": "munikis", "terms": ["尼比斯零", "尼比斯", "虛無歸零", "munikis", "ムニキスゼロ", "munikis zero"]},
    {"id": "fest", "terms": ["太晶慶典", "terastalfestival", "テラスタルフェス", "terastal festival"]},
    {"id": "shinybox", "terms": ["閃色寶藏", "shinytreasure", "シャイニートレジャー", "shiny treasure"]},
    {"id": "battle", "terms": ["對戰夥伴", "battlepartners", "バトルパートナーズ", "battle partners"]},
    {"id": "stellar", "terms": ["星晶奇跡", "stellarmiracle", "ステラミラクル", "stellar miracle"]},
    {"id": "glory", "terms": ["火箭隊的榮耀", "ロケット団の栄光", "gloryoftheteamrocket", "glory of team rocket"]},
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
    {"id": "shiny", "exclusive": True, "needles": ["閃色寶藏", "シャイニートレジャー", "shiny treasure", "sv4a"]},
    {"id": "sv151", "exclusive": True, "needles": ["sv2a"]},
    {"id": "obsidian", "exclusive": True, "needles": ["黑炎", "黒炎", "blackflame", "obsidian", "sv3"]},
    {"id": "electric", "exclusive": True, "needles": ["超電", "superelectric", "super electric"]},
    {"id": "heroes", "exclusive": True, "needles": ["伊布英雄", "イーブイヒーローズ", "eevee heroes", "eeveeheroes"]},
    {"id": "vstar", "exclusive": False, "needles": ["vstar"]},
]

_NON_JP = (
    "繁中", "繁體", "繁体", "中文版", "港版", "台版", "台灣版", "简中", "簡中",
    "韓版", "korean", "英文版", "美版", "英版", "歐版", "(cn)", "(hk)", "(tw)", "(kr)",
    "中国語", "中国版", "簡体", "简体", "アジア版", "英語版", "韓国",
)
_SEEK = ("求購", "收購", "高價收", "wtb", "wanted", "looking for", "求卡", "想收", "收卡")
_CODE_RE = re.compile(r"(?<![a-z])((?:sv|s|m)\d+[a-z]*)(?![a-z])")
_JP_OK = ("日版", "日文", "japanese", "(jp)", "日本", " jp")

_LOT = ("十連", "連號", "sequential", "set of", "lot of", "一套")
_JUNK = (
    "福袋", "oripa", "抽池", "刮卡", "mezastar", "明耀之星", "plamo", "組裝模型", "退坑",
    "禮盒", "礼盒", "まとめ", "大量", "ジャンク", "オリパ",
)


def _item_blob(item: dict) -> str:
    """Names plus the set code that agrees with tcgdex. A stale set field is left out."""
    parts = [
        str(item.get(key) or "")
        for key in ("search_hk", "name_zh", "name_jp", "search_jp")
    ]
    codes = _identity_codes(item)
    if codes:
        parts.append(" ".join(sorted(codes)))
    elif item.get("set"):
        parts.append(str(item.get("set")))
    return " ".join(part for part in parts if part)


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


def _has_set_151(text: str) -> bool:
    """151 as a set name, not the left or right side of a collector number."""
    stripped = re.sub(r"\d{1,3}\s*/\s*\d{1,3}", " ", text)
    n = _norm(stripped)
    return "sv2a" in n or "151" in n


def _has_shiny_set(text: str) -> bool:
    n = _norm(text)
    if any(bit in n for bit in ("sv4a", "閃色寶藏", "shinytreasure", "シャイニートレジャー")):
        return True
    return re.search(r"閃(?!卡)", text) is not None


def _hits_n_sar(text_n: str) -> bool:
    """N SAR, not the 'n'+'sar' inside a longer Latin name."""
    if re.search(r"(?<![a-z])ns+ar", text_n):
        return True
    return "エヌ" in text_n and "sar" in text_n


def _marker_ids(text: str) -> set[str]:
    n = _norm(text)
    found: set[str] = set()
    for marker in _MARKERS:
        if marker["id"] == "sv151":
            if _has_set_151(text):
                found.add("sv151")
            continue
        if marker["id"] == "shiny":
            if _has_shiny_set(text):
                found.add("shiny")
            continue
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
    if _has_set_151(text) and all(group["id"] != "sv151" for group in kept):
        kept.append(next(group for group in _GROUPS if group["id"] == "sv151"))
    return kept


_SEALED_SET_MEGA = (
    "超級夢想", "超級勇氣", "超級協奏",
    "mega dream", "mega brave", "mega symphonia", "mega siphonia",
    "メガドリーム", "メガブレイブ", "メガシンフォニア",
)


def _required_markers(query: str) -> set[str]:
    """Mega Dream / Brave / Symphonia use 超級 in the set name, not as a slab mechanic."""
    found = _marker_ids(query)
    if "mega" not in found:
        return found
    stripped = query
    for bit in _SEALED_SET_MEGA:
        stripped = re.sub(re.escape(bit), " ", stripped, flags=re.I)
    if "mega" not in _marker_ids(stripped):
        found = set(found)
        found.discard("mega")
    return found


def _title_hits_group(
    title_n: str,
    group: dict[str, Any],
    query_n: str,
    title: str = "",
    card_number: str | None = None,
) -> bool:
    if group["id"] == "sv151":
        if _has_set_151(title or title_n):
            return True
        return bool(card_number and card_number in _frac_nums(title))
    if group["id"] == "nsar":
        return _hits_n_sar(title_n)
    excludes = [_norm(x) for x in group.get("excludes") or []]
    if any(x and x in title_n for x in excludes):
        return False
    if not any(_norm(t) and _norm(t) in title_n for t in group["terms"]):
        return False
    for aliases in group.get("specific") or []:
        norms = [_norm(a) for a in aliases]
        if any(a and a in query_n for a in norms) and not any(a and a in title_n for a in norms):
            return False
    return True


def _wants_charizard_x(text: str) -> bool:
    n = _norm(text)
    return any(s in n for s in ("噴火龍x", "charizardx", "リザードンx"))


def _title_charizard_x_ok(title_n: str, query: str) -> bool:
    """X and Y are different cards. A plain 噴火龍 title is not Charizard X."""
    has_x = any(s in title_n for s in ("噴火龍x", "charizardx", "リザードンx"))
    has_y = any(s in title_n for s in ("噴火龍y", "charizardy", "リザードンy"))
    if _wants_charizard_x(query):
        return has_x and not has_y
    return not has_x and not has_y


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
    if "カートン" in title and "カートン" not in query:
        return True
    return False


def _non_jp(title: str) -> bool:
    low = title.lower()
    if any(bit in low for bit in _NON_JP) and not any(bit in low for bit in _JP_OK):
        return True
    return False


def _grade_score(row: dict | None) -> float | None:
    if not row or row.get("grade_score") is None:
        return None
    try:
        return float(row["grade_score"])
    except (TypeError, ValueError):
        return None


def _is_seek(title: str) -> bool:
    low = title.lower()
    if any(bit in low for bit in _SEEK):
        return True
    return re.search(r"(^|\s)收(?!納|藏)", title) is not None


def _wrong_grade(title: str) -> bool:
    """PSA 9 / BGS / raw, or a title that mixes PSA10 with another grade."""
    if re.search(r"\b(bgs|cgc|ars|sgc)\b|裸卡|未評", title, re.I):
        return True
    other = re.search(r"psa\s*[1-9](?!\d)", title, re.I) is not None
    if other:
        return True
    return False


def _is_psa10(title: str, row: dict | None) -> bool:
    if _wrong_grade(title):
        return False
    score = _grade_score(row)
    company = str((row or {}).get("grade_company") or "").upper()
    if score is not None:
        if company and company != "PSA":
            return False
        return score >= 10
    return "psa10" in _norm(title)


def _is_box(title: str) -> bool:
    return re.search(r"booster\s*box|\bbox\b|原盒|未開封|ボックス", title, re.I) is not None


def _sealed_side_product(title: str) -> bool:
    """Packs, decks, ETBs, figurines, and gift sets are not the booster box ask."""
    if re.search(
        r"elite trainer|\betb\b|collection|收藏箱|禮盒|礼盒|構築|牌組|新手|預組|入門|deck|figurine|\bchinese\b",
        title,
        re.I,
    ):
        return True
    if re.search(r"booster\s*box|原盒|ボックス|\bbox\b", title, re.I):
        return False
    if re.search(r"開封済|開封済み", title) and "未開封" not in title:
        return True
    return re.search(r"補充包|單包|\bpack\b|卡包|パック", title, re.I) is not None


def _set_codes(text: str) -> set[str]:
    """Set codes from the raw title so 'PTCG M2a' is not glued into 'ptcgm2a'."""
    return {code.lower() for code in _CODE_RE.findall(text.lower())}


def _code_conflict(query: str, title: str) -> bool:
    """Different set codes are different products (M2 vs M2a, SV2a vs M2a, SV2a vs SV9a)."""
    query_codes = _set_codes(query)
    title_codes = _set_codes(title)
    if not query_codes or not title_codes:
        return False
    return not (query_codes & title_codes)


# Set code → product-name group. A title may say 151 or 黑炎 instead of SV2a / SV3.
_CODE_FOR_GROUP = {
    "sv151": "sv2a",
    "blackflame": "sv3",
    "shinybox": "sv4a",
    "electric": "sv8",
    "fest": "sv8a",
    "dream": "m2a",
    "brave": "m1l",
    "symphonia": "m1s",
    "inferno": "m2",
    "ninja": "m4",
    "abyss": "m5",
    "storm": "m6",
    "munikis": "m3",
    "bolt": "sv11b",
    "flare": "sv11w",
    "ancient": "sv4k",
    "stellar": "sv7",
    "battle": "sv9",
    "glory": "sv10",
    "heroes": "s6a",
}


def _alias_hit(query: str, title: str) -> bool:
    """True when the title uses the set's name rather than its code."""
    codes = _set_codes(query)
    if not codes:
        return False
    title_n = _norm(title)
    if "sv2a" in codes and _has_set_151(title):
        return True
    if "sv4a" in codes and _has_shiny_set(title):
        return True
    if "sv3" in codes and any(bit in title_n for bit in ("黑炎", "黒炎", "obsidian")):
        return True
    if "sv8" in codes and "超電" in title:
        return True
    for group in _GROUPS:
        code = _CODE_FOR_GROUP.get(group["id"])
        if code not in codes:
            continue
        for term in group["terms"]:
            term_n = _norm(term)
            if term_n and term_n in title_n:
                return True
    return False


def _identity_aligned(
    query: str,
    title: str,
    *,
    number_hit: bool,
    card_number: str | None,
) -> bool:
    """Set code, its public name, or the collector number must show up on the title.

    Name-only hits (噴火龍 with no 151 / SV2a / 201) are rejected once the watchlist
    item actually has a set code or a collector number.
    """
    codes = _set_codes(query)
    if not codes and not card_number:
        return True
    if card_number and number_hit:
        return True
    if codes & _set_codes(title):
        return True
    return _alias_hit(query, title)


def _frac_nums(title: str) -> list[str]:
    return re.findall(r"(\d{2,3})\s*/\s*\d{2,3}", title)


def _has_token(text: str, token: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)", text.lower()) is not None


def _stated_rarity_conflict(title: str, query: str) -> bool:
    """A title that names a different rarity is not this card, even with the same number."""
    if _has_token(query, "sr") and not _has_token(query, "sar"):
        return _has_token(title, "sar") or _has_token(title, "ar")
    if not (_has_token(query, "sar") or "special art" in query.lower()):
        return False
    if _has_token(title, "ar"):
        return True
    if _has_token(title, "sar") or "special art" in title.lower():
        return False
    return any(_has_token(title, tok) for tok in ("sr", "ur", "hr", "rr"))


def _without_set_ex(text: str) -> str:
    """シャイニートレジャーex is the set name, not a Pokémon ex."""
    cleaned = text
    for phrase in (
        "シャイニートレジャーex",
        "テラスタルフェスex",
        "メガドリームex",
        "shiny treasure ex",
        "terastal fest ex",
    ):
        cleaned = re.sub(re.escape(phrase), phrase[:-2], cleaned, flags=re.I)
    return cleaned


def _stage_conflict(title: str, query: str) -> bool:
    """A title that names a different stage is another card. Omitting ex is allowed."""
    title = _without_set_ex(title)
    query = _without_set_ex(query)
    title_n = _norm(title)
    query_n = _norm(query)
    for token in ("vmax", "vstar"):
        if token in title_n and token not in query_n:
            return True
    return _has_token(title, "ex") and not _has_token(query, "ex")


def _wants_illustration_rare(query: str) -> bool:
    if _has_token(query, "sar") or "special art" in query.lower():
        return False
    return bool(_has_token(query, "ar") or "イラストレア" in query or "アートレア" in query)


def _is_illustration_rare(title: str) -> bool:
    return bool(
        _has_token(title, "ar")
        or "イラストレア" in title
        or "アートレア" in title
        or "illustration rare" in title.lower()
    )


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


def _identity_codes(item: dict) -> set[str]:
    """Prefer tcgdex when `set` names a different product.

    Read the raw fields. Normalizing first glues SV9-127 into a fake code sv9127.
    """
    tcg_codes = _set_codes(str(item.get("tcgdex_id") or ""))
    set_codes = _set_codes(str(item.get("set") or ""))
    if tcg_codes and set_codes and not (tcg_codes & set_codes):
        return tcg_codes
    return tcg_codes | set_codes


def _card_print(item: dict) -> tuple[str, str | None] | None:
    """Full set fraction when it belongs to the same set code as tcgdex; else the tcgdex number."""
    tcg = str(item.get("tcgdex_id") or "")
    set_field = str(item.get("set") or "")
    tcg_codes = _set_codes(tcg)
    set_codes = _set_codes(set_field)
    conflict = bool(tcg_codes and set_codes and not (tcg_codes & set_codes))
    code_nums = {digits for code in (tcg_codes | set_codes) for digits in re.findall(r"\d+", code)}
    if not conflict:
        found = re.findall(r"(\d{2,3})\s*/\s*(\d{2,3})", set_field)
        if found:
            num, den = found[-1]
            # "S11 / 125" is the set number and the collector number, not 11/125.
            if num not in code_nums:
                return num, den
    match = re.search(r"-(\d{2,3})\b", tcg)
    if not match:
        return None
    return match.group(1), None


def _bare_collector_conflict(title: str, card_number: str | None) -> bool:
    """sv5k 097 is not SV5K-088. 151 in a set name is not a collector number."""
    if not card_number:
        return False
    stripped = re.sub(r"\d{1,3}\s*/\s*\d{1,3}", " ", title)
    nums = re.findall(r"(?<!\d)(\d{3})(?!\d)", stripped)
    collectors = [num for num in nums if not num.startswith(("19", "20"))]
    if not collectors:
        return False
    if card_number in collectors:
        return False
    if collectors == ["151"] and _has_set_151(title):
        return False
    return True


def _print_hit(title: str, card_number: str | None, card_denom: str | None) -> bool:
    if not card_number:
        return False
    pairs = re.findall(r"(\d{2,3})\s*/\s*(\d{2,3})", title)
    if card_denom:
        return any(num == card_number and den == card_denom for num, den in pairs)
    return any(num == card_number for num, _ in pairs)


def _specific_name_hit(title: str, query: str) -> bool:
    """エリカの招待 / ロケット団のミュウツー, not a shared name like ピカチュウ or ナンジャモ."""
    title_n = _norm(title)
    query_n = _norm(query)
    for group in _groups_in(query):
        aliases = group.get("specific") or []
        norms = [_norm(alias) for bundle in aliases for alias in bundle]
        if any(alias and alias in query_n for alias in norms) and any(
            alias and alias in title_n for alias in norms
        ):
            return True
    return False


def match_item(
    rows: list[dict],
    item: dict,
    *,
    apply_price_band: bool = True,
    require_print: bool = False,
    extra_query: str = "",
) -> list[dict]:
    codes = _identity_codes(item)
    keyword_parts = [str(item.get("search_hk") or ""), extra_query]
    if codes:
        keyword_parts.append(" ".join(sorted(codes)))
    elif item.get("set"):
        keyword_parts.append(str(item.get("set")))
    printed = _card_print(item)
    number, denom = printed if printed else (None, None)
    if (item.get("kind") or "psa10") == "psa10":
        require_print = True
    return match_listings(
        rows,
        keyword=" ".join(part for part in keyword_parts if part),
        kind=item.get("kind") or "psa10",
        name_jp=item.get("name_jp"),
        name_zh=item.get("name_zh"),
        card_number=number,
        card_denom=denom,
        apply_price_band=apply_price_band,
        require_print=require_print,
    )


_BUY_LISTING_TYPES = {"want", "wanted", "wtb", "buy", "bid", "seek", "demand", "buying"}


def match_listings(
    rows: list[dict],
    *,
    keyword: str,
    kind: str,
    name_jp: str | None = None,
    name_zh: str | None = None,
    card_number: str | None = None,
    card_denom: str | None = None,
    apply_price_band: bool = True,
    require_print: bool = False,
) -> list[dict]:
    query = " ".join(x for x in (keyword, name_jp or "", name_zh or "") if x)
    query_n = _norm(query)
    groups = _groups_in(query)
    if not groups:
        return []
    query_markers_all = _marker_ids(query)
    query_markers = _required_markers(query)
    hits: list[dict] = []
    for row in rows:
        title = str(row.get("card_name") or row.get("title") or "")
        if not title or _non_jp(title) or _is_seek(title) or _is_lot(title, _norm(title)):
            continue
        listing_type = str(row.get("listing_type") or "").lower()
        if listing_type in _BUY_LISTING_TYPES:
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
        number_hit = _print_hit(title, card_number, card_denom)
        if kind == "psa10":
            if (
                not _is_psa10(title, row)
                or _is_product_not_slab(title)
                or _stated_rarity_conflict(title, query)
                or (not number_hit and not _rarity_ok(title, query))
            ):
                continue
            if apply_price_band and (price < 80 or price > 200_000):
                continue
            if _stage_conflict(title, query):
                continue
            if _wants_illustration_rare(query) and (
                not _is_illustration_rare(title) or _has_token(title, "sar")
            ):
                continue
            if card_number and _frac_nums(title) and not number_hit:
                continue
            if not number_hit and _bare_collector_conflict(title, card_number):
                continue
            if require_print and card_number and not number_hit:
                if not (
                    _specific_name_hit(title, query)
                    and not _bare_collector_conflict(title, card_number)
                ):
                    continue
        elif kind == "sealed":
            if _sealed_side_product(title):
                continue
            if re.search(r"原箱|カートン", title):
                continue
            multi = re.search(r"(?<!\d)(\d{1,2})\s*盒", title)
            if multi and int(multi.group(1)) >= 2:
                continue
            multi_box = re.search(r"(?<!\d)(\d{1,2})\s*(?:box|ボックス|箱)", title, re.I)
            if multi_box and int(multi_box.group(1)) >= 2:
                continue
            if re.search(r"[×✕]\s*[2-9]", title):
                continue
            if "点セット" in title:
                continue
            if not _is_box(title):
                continue
            if apply_price_band and (price < 80 or price > 25_000):
                continue
        else:
            continue
        if not all(
            _title_hits_group(title_n, group, query_n, title, card_number) for group in groups
        ):
            continue
        query_chars = {g["id"] for g in groups if g["id"] not in _SET_IDS}
        title_chars = [g["id"] for g in _groups_in(title) if g["id"] not in _SET_IDS]
        if any(gid not in query_chars for gid in title_chars):
            continue
        query_sets = {g["id"] for g in groups if g["id"] in _SET_IDS}
        title_sets = [g["id"] for g in _groups_in(title) if g["id"] in _SET_IDS]
        if query_sets and any(gid not in query_sets for gid in title_sets):
            continue
        if _code_conflict(query, title):
            continue
        title_markers = _marker_ids(title)
        if number_hit:
            for waived in ("sv151", "shiny", "obsidian", "electric"):
                if waived in query_markers:
                    title_markers.add(waived)
        if any(marker not in title_markers for marker in query_markers):
            continue
        if any(
            m["exclusive"] and m["id"] in title_markers and m["id"] not in query_markers_all
            for m in _MARKERS
        ):
            continue
        if not _title_charizard_x_ok(title_n, query):
            continue
        if not _identity_aligned(
            query, title, number_hit=number_hit, card_number=card_number
        ):
            continue
        code_hit = bool(_set_codes(query) & _set_codes(title))
        url = row.get("url")
        hits.append(
            {
                "id": row.get("id"),
                "title": title,
                "price_hkd": price,
                "source": row.get("source"),
                "url": str(url) if url else None,
                "strong": bool(number_hit or code_hit),
            }
        )
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


def _blank_ask() -> dict[str, Any]:
    return {"hkd": None, "match_count": 0, "example_url": None, "listings": []}


def _within_jp_band(price: float, jp_hkd: float | None) -> bool:
    """Absurd asks are under 10% or over 300% of the JP sold median."""
    if jp_hkd is None or jp_hkd <= 0:
        return True
    ratio = price / float(jp_hkd)
    return 0.10 <= ratio <= 3.0


def _dedupe_listings(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for row in rows:
        key = (
            str(row.get("source") or ""),
            str(row.get("id") or row.get("title") or ""),
            str(row.get("price_hkd") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _closest_url(rows: list[dict], price: float) -> str | None:
    if not rows:
        return None
    best = min(rows, key=lambda row: abs(float(row["price_hkd"]) - price))
    url = best.get("url")
    return str(url) if url else None


def publish_ask(listings: list[dict], jp_hkd: float | None) -> dict[str, Any]:
    """Price we are willing to show as 香港最新賣出價.

    Several matches inside 10–300% of the JP sold median publish their median.
    One listing is kept only when the title carries the set code or collector
    number and the price is inside that band. Anything else becomes no ask.
    """
    banded: list[dict] = []
    for row in _dedupe_listings(listings):
        try:
            price = float(row.get("price_hkd"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if _within_jp_band(price, jp_hkd):
            banded.append(row)
    pool = banded
    if len(pool) >= 2:
        vals = trimmed_asks([float(row["price_hkd"]) for row in pool])
        kept_keys = {round(val, 2) for val in vals}
        used = [row for row in pool if round(float(row["price_hkd"]), 2) in kept_keys]
        mid = robust_median(vals)
        if mid is None or not used:
            return _blank_ask()
        return {
            "hkd": mid,
            "match_count": len(used),
            "example_url": _closest_url(used, mid),
            "listings": used,
        }
    if (
        len(pool) == 1
        and pool[0].get("strong")
        and _within_jp_band(float(pool[0]["price_hkd"]), jp_hkd)
    ):
        row = pool[0]
        price = round(float(row["price_hkd"]), 2)
        url = row.get("url")
        return {
            "hkd": price,
            "match_count": 1,
            "example_url": str(url) if url else None,
            "listings": [row],
        }
    return _blank_ask()
