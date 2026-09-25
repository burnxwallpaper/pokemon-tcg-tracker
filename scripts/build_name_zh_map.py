"""Build data/name_zh_map.json from PokeAPI zh-Hant plus official HK/TW set titles.

Species and form names: PokeAPI language 11 (ja) → language 4 (zh-Hant).
Set titles: TCGdex Japanese names joined to asia.pokemon-card.com (zh-cmn-Hant-HK)
by set code. SV4a on TCGdex is mislabeled レイジングサーフ; the official pair is
シャイニートレジャーex → 閃色寶藏ex. SVK's Japanese and HK products do not match,
so that pair is left out.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "data" / "name_zh_map.json"
_QUOTE = re.compile(r"「([^」]+)」")
_FULLWIDTH_LATIN = str.maketrans({"Ｘ": "X", "Ｙ": "Y", "Ｚ": "Z", "Ｎ": "N"})

_SPECIES_URL = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
    "pokemon_species_names.csv"
)
_FORMS_URL = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
    "pokemon_form_names.csv"
)

# (Japanese title, official HK/TW product label). Inner 「」 becomes the set key.
_SET_PAIRS: tuple[tuple[str, str], ...] = (
    ("ストームエメラルダ", "擴充包「綠寶石風暴」"),
    ("アビスアイ", "擴充包「深淵之瞳」"),
    ("ニンジャスピナー", "擴充包「忍者飛旋」"),
    ("ムニキスゼロ", "擴充包「虛無歸零」"),
    ("スタートデッキ100 バトルコレクション", "初階牌組100對戰收藏"),
    ("MEGAドリームex", "高級擴充包「超級進化夢想ex」"),
    ("インフェルノX", "擴充包「烈獄狂火X」"),
    ("メガシンフォニア", "擴充包「超級交響樂」"),
    ("メガブレイブ", "擴充包「超級勇氣」"),
    ("メガ プロモカード", "特典卡 超級進化"),
    ("ブラックボルト", "擴充包「漆黑伏特」"),
    ("ホワイトフレア", "擴充包「純白閃焰」"),
    ("ロケット団の栄光", "擴充包「火箭隊的榮耀」"),
    ("熱風のアリーナ", "強化擴充包「熱風競技場」"),
    ("バトルパートナーズ", "擴充包「對戰搭檔」"),
    ("テラスタルフェスex", "高級擴充包「太晶慶典ex」"),
    ("超電ブレイカー", "擴充包「超電突圍」"),
    ("楽園ドラゴーナ", "強化擴充包「樂園騰龍」"),
    ("ステラミラクル", "擴充包「星晶奇跡」"),
    ("ナイトワンダラー", "強化擴充包「黑夜漫遊者」"),
    ("変幻の仮面", "擴充包「變幻假面」"),
    ("クリムゾンヘイズ", "強化擴充包「緋紅薄霧」"),
    ("サイバージャッジ", "擴充包「異度審判」"),
    ("ワイルドフォース", "擴充包「狂野之力」"),
    ("未来の一閃", "擴充包「未來閃光」"),
    ("古代の咆哮", "擴充包「古代咆哮」"),
    ("レイジングサーフ", "強化擴充包「激狂駭浪」"),
    ("黒炎の支配者", "擴充包「黯焰支配者」"),
    ("ポケモンカード151", "強化擴充包「寶可夢卡牌151」"),
    ("スノーハザード", "擴充包「冰雪險境」"),
    ("クレイバースト", "擴充包「碟旋暴擊」"),
    ("トリプレットビート", "強化擴充包「三連音爆」"),
    ("バイオレットex", "擴充包「紫ex」"),
    ("スカーレットex", "擴充包「朱ex」"),
    ("スカーレット&バイオレット プロモカード", "特典卡 朱&紫"),
    ("VSTARユニバース", "高級擴充包「天地萬物VSTAR」"),
    ("パラダイムトリガー", "擴充包「思維激盪」"),
    ("白熱のアルカナ", "強化擴充包「白熱奧祕」"),
    ("ロストアビス", "擴充包「迷途深淵」"),
    ("Pokémon GO", "強化擴充包「Pokémon GO」"),
    ("ダークファンタズマ", "強化擴充包「黑暗亡靈」"),
    ("スペースジャグラー", "擴充包「空間魔術師」"),
    ("タイムゲイザー", "擴充包「時間觀察者」"),
    ("バトルリージョン", "強化擴充包「對戰地區」"),
    ("スターバース", "擴充包「星星誕生」"),
    ("VMAXクライマックス", "高級擴充包「VMAX絕群壓軸」"),
    ("25th アニバーサリーコレクション", "擴充包「25週年收藏款」"),
    ("フュージョンアーツ", "擴充包「匯流藝術」"),
    ("蒼空ストリーム", "擴充包「蒼空烈流」"),
    ("摩天パーフェクト", "擴充包「摩天巔峰」"),
    ("イーブイヒーローズ", "強化擴充包「伊布英雄」"),
    ("白銀のランス", "擴充包「銀白戰槍」"),
    ("漆黒のガイスト", "擴充包「漆黑幽魂」"),
    ("双璧のファイター", "強化擴充包「雙璧戰士」"),
    ("連撃マスター", "擴充包「連擊大師」"),
    ("一撃マスター", "擴充包「一擊大師」"),
    ("シャイニースターV", "高級擴充包「閃色明星V」"),
    ("仰天のボルテッカー", "擴充包「驚天伏特攻擊」"),
)

_EXTRA_SETS: dict[str, str] = {
    "シャイニートレジャーex": "閃色寶藏ex",
    "シャイニートレジャー": "閃色寶藏",
    "メガドリームex": "超級進化夢想ex",
    "熱風アリーナ": "熱風競技場",
    "25th ANNIVERSARY COLLECTION": "25週年收藏款",
    "25th ANNIVERSARY edition": "25週年紀念版",
    "25th アニバーサリー コレクション": "25週年收藏款",
    "25th アニバーサリー": "25週年紀念",
    "バトルコレクション": "對戰收藏",
}

# Card titles whose の-phrase is not just trainer + species.
_PHRASES: dict[str, str] = {
    "リーリエの決心": "莉莉艾的決意",
    "アセロラのいたずら": "阿塞蘿拉的惡作劇",
    "エリカの招待": "莉佳的招待",
    "シロナの覇気": "竹蘭的霸氣",
    "メイのはげまし": "鳴依的勉勵",
    "ヒガナの信頼": "希嘉娜的信賴",
    "カミツレのきらめき": "小菊兒的閃耀",
    "ルチアのアピール": "露琪亞的吸引力",
    "ヒビキのホウオウ": "阿響的鳳王",
    "名探偵ピカチュウ": "名偵探皮卡丘",
    "ゴッホピカチュウ": "梵高皮卡丘",
    "なみのりピカチュウ": "衝浪皮卡丘",
    "そらをとぶピカチュウ": "飛行皮卡丘",
    "お誕生日ピカチュウ": "生日皮卡丘",
    "海で遊ぶピカチュウ": "海邊玩耍皮卡丘",
    "漫才ごっこピカチュウ": "漫才表演皮卡丘",
    "ひかるセレビィ": "閃耀時拉比",
    "わるいギャラドス": "邪惡暴鯉龍",
    "ふしぎなしっぽ": "神秘尾巴",
    "マスボピカチュウ": "大師球皮卡丘",
    "ムービースペシャルパック": "電影特別包",
    "ポケモンワールドチャンピオンシップス2023横浜": "寶可夢世界錦標賽2023橫濱",
    "ポケモン切手BOX": "寶可夢郵票BOX",
    "見返り美人・月に雁": "迴眸美人・月下雁",
    "マクドナルド": "麥當勞",
    "ハッピーセット": "開心樂園餐",
    "YU NAGABA×ポケモンカードゲーム": "YU NAGABA×寶可夢卡牌遊戲",
    "基本拡張パック": "基本擴充包",
}

_TRAINERS: dict[str, str] = {
    "ナンジャモ": "奇樹",
    "リーリエ": "莉莉艾",
    "アセロラ": "阿塞蘿拉",
    "カミツレ": "小菊兒",
    "エリカ": "莉佳",
    "シロナ": "竹蘭",
    "マリィ": "瑪俐",
    "セレナ": "莎莉娜",
    "カナリィ": "卡娜莉",
    "ヒカリ": "小光",
    "サトシ": "小智",
    "レッド": "赤紅",
    "ルリナ": "露璃娜",
    "メロン": "美蓉",
    "スグリ": "烏栗",
    "ゼイユ": "丹瑜",
    "メイ": "鳴依",
    "ヒガナ": "希嘉娜",
    "ロケット団": "火箭隊",
    "ミモザ": "米莫莎",
    "ルチア": "露琪亞",
    "ヒビキ": "阿響",
    "オリーヴ": "奧利薇",
}

_PLACES: dict[str, str] = {
    "トウホク": "東北",
    "ヒロシマ": "廣島",
    "フクオカ": "福岡",
    "カナザワ": "金澤",
    "ヨコハマ": "橫濱",
    "横浜": "橫濱",
}

_PRODUCT: dict[str, str] = {
    "ポケモンカードゲームMEGA": "寶可夢卡牌遊戲MEGA",
    "ポケモンカードゲーム Classic": "寶可夢卡牌遊戲 Classic",
    "ポケットモンスターカードゲーム": "寶可夢卡牌遊戲",
    "ポケモンカードゲーム": "寶可夢卡牌遊戲",
    "スカーレット&バイオレット": "朱&紫",
    "ソード&シールド": "劍&盾",
    "強化拡張パック": "強化擴充包",
    "ハイクラスパック": "高級擴充包",
    "コンセプトパック": "概念包",
    "拡張パック": "擴充包",
    "スペシャルデッキセットex": "特別牌組組合ex",
    "スペシャルデッキセット": "特別牌組組合",
    "プレミアムデッキセット": "頂級牌組組合",
    "スタートデッキ100": "初階牌組100",
    "スタートデッキ": "初階牌組",
    "スターターセット": "起始組合",
    "デッキビルドBOX": "牌組構築BOX",
    "構築デッキ": "構築牌組",
    "記念デッキ": "紀念牌組",
    "プロモカードパック": "特典卡包",
    "プロモーションカード": "特典卡",
    "プロモカード": "特典卡",
    "スペシャルBOX": "特別BOX",
    "特別セット": "特別組合",
    "ゴールデンボックス": "黃金盒",
    "ポケモンセンター": "寶可夢中心",
    "ポケモンカード": "寶可夢卡牌",
    "ボックス": "BOX",
    "デッキ": "牌組",
    "セット": "組合",
    "争奪戦": "爭奪戰",
    "構築戦": "構築戰",
    "上位賞": "上位獎",
    "シュリンク付き": "有膠膜",
    "シュリンク": "膠膜",
    "ビニールなし": "無膠套",
    "フルイラスト": "全圖",
    "マークあり": "有印記",
    "付録": "附錄",
    "月号": "月號",
    "仕様": "樣式",
}

# Japanese words only. Latin rarity codes stay in rarity_labels.
_RARITY: dict[str, str] = {
    "マスターボール": "大師球",
    "モンスターボール": "精靈球",
    "プロモ": "特典",
    "ミラー": "反光",
    "ノーマル": "普通",
    "1ED": "初版",
}

_RARITY_LABELS: dict[str, str] = {
    "C": "普通",
    "U": "非普通",
    "R": "稀有",
    "RR": "雙稀有",
    "RRR": "三稀有",
    "AR": "藝術稀有",
    "SR": "超稀有",
    "SAR": "特別插畫稀有",
    "UR": "極稀有",
    "HR": "彩虹稀有",
    "CSR": "角色超稀有",
    "CHR": "角色稀有",
    "SSR": "閃色超稀有",
    "ACE": "ACE SPEC",
    "S": "閃",
    "K": "稀有閃",
    "A": "驚人稀有",
    "PR": "稜鏡稀有",
    "TR": "訓練家稀有",
    "MA": "超級攻擊稀有",
    "MUR": "超級極稀有",
    "BWR": "黑白稀有",
    "無標記": "無標記",
}

_FORM_PREFIXES: dict[str, str] = {
    "テラスタル": "太晶",
    "アローラ": "阿羅拉",
    "パルデア": "帕底亞",
    "オリジン": "起源",
    "ガラル": "伽勒爾",
    "ヒスイ": "洗翠",
    "わるい": "邪惡",
    "メガ": "超級",
}

_SKIP_FORMS = {"オス", "メス", "普通"}


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "pokemon-tcg-tracker-name-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8")


def _read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _halfwidth(text: str) -> str:
    return text.translate(_FULLWIDTH_LATIN)


def _sorted(table: dict[str, str]) -> dict[str, str]:
    return dict(sorted(table.items()))


def _ampersand_variants(table: dict[str, str]) -> dict[str, str]:
    extra: dict[str, str] = {}
    for key, value in table.items():
        if "&" not in key and "＆" not in key:
            continue
        compact = key.replace(" ", "").replace("＆", "&")
        for variant in (
            compact,
            compact.replace("&", "＆"),
            compact.replace("&", " & "),
            compact.replace("&", " ＆ "),
        ):
            extra.setdefault(variant, value)
    merged = dict(table)
    merged.update(extra)
    return merged


def _species(rows: list[dict[str, str]]) -> dict[str, str]:
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        by_id.setdefault(row["pokemon_species_id"], {})[row["local_language_id"]] = row["name"]
    out: dict[str, str] = {}
    for names in by_id.values():
        ja = names.get("11") or names.get("1") or ""
        zh = names.get("4") or ""
        if len(ja) >= 2 and zh and ja != zh:
            out[ja] = zh
    return out


def _forms(rows: list[dict[str, str]], species: dict[str, str]) -> dict[str, str]:
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        by_id.setdefault(row["pokemon_form_id"], {})[row["local_language_id"]] = row["form_name"]
    out: dict[str, str] = dict(_FORM_PREFIXES)
    pending_mega: list[str] = []
    for names in by_id.values():
        ja = names.get("11") or names.get("1") or ""
        zh = names.get("4") or ""
        if len(ja) < 2 or ja in _SKIP_FORMS:
            continue
        if zh and ja != zh:
            out[ja] = zh
            half = _halfwidth(ja)
            if half != ja:
                out[half] = _halfwidth(zh)
        elif ja.startswith("メガ"):
            pending_mega.append(ja)
    for ja in pending_mega:
        if ja in out:
            continue
        rest = ja[2:]
        suffix = ""
        for token in ("Ｘ", "Ｙ", "Ｚ", "X", "Y", "Z"):
            if rest.endswith(token):
                suffix = _halfwidth(token)
                rest = rest[: -len(token)]
                break
        species_zh = species.get(rest)
        if species_zh:
            out[ja] = f"超級{species_zh}{suffix}"
            half = _halfwidth(ja)
            if half != ja:
                out[half] = out[ja]
    return out


def _sets() -> dict[str, str]:
    out: dict[str, str] = {}
    for ja, label in _SET_PAIRS:
        quoted = _QUOTE.search(label)
        zh = quoted.group(1).strip() if quoted else re.sub(r"\s+", "", label)
        if ja and zh and ja != zh:
            out[ja] = zh
    out.update(_EXTRA_SETS)
    return out


def _examples() -> list[dict[str, str]]:
    from name_zh_map import clear_cache, rarity_label, translate

    clear_cache()
    samples = (
        "ピカチュウ",
        "ゲッコウガex SAR",
        "ミュウツー",
        "メガニウム",
        "メガリザードンX",
        "アローラロコン",
        "ステラミラクル BOX",
        "拡張パック「黒炎の支配者」",
        "リーリエの決心 SR",
        "ゴッホピカチュウ",
        "マスターボールミラー",
        "MレックウザEX",
    )
    rows = [{"jp": sample, "zh": translate(sample)} for sample in samples]
    gloss = rarity_label("SAR")
    if gloss:
        rows.append({"jp": "SAR", "zh": gloss, "via": "rarity_label"})
    return rows


def build(species_csv: str, forms_csv: str) -> dict[str, object]:
    species = _species(_read_csv(species_csv))
    forms = _forms(_read_csv(forms_csv), species)
    sets = _sets()
    groups = {
        "phrases": _PHRASES,
        "sets": _ampersand_variants(sets),
        "forms": forms,
        "species": species,
        "trainers": _TRAINERS,
        "places": _PLACES,
        "product": _ampersand_variants(_PRODUCT),
        "rarity": _RARITY,
    }
    counts = {name: len(table) for name, table in groups.items()}
    counts["rarity_labels"] = len(_RARITY_LABELS)
    counts["replace_entries"] = sum(counts[name] for name in groups)
    return {
        "locale": "zh-Hant",
        "style": "HK/TW official",
        "match": "longest-key-first",
        "import": "scripts/name_zh_map.py — translate(text) uses replace_groups; rarity_label(code) is exact",
        "replace_groups": list(groups),
        "rules": {
            "possessive_no": "After replacement, の between non-kana characters becomes 的.",
            "mega_m": "A lone M immediately before a Chinese character becomes 超級 (XY Mega prefix).",
            "rarity_labels": "Exact code lookup only. translate() leaves SAR/SR/UR in the title.",
        },
        "sources": {
            "species": "PokeAPI pokemon_species_names, language_id 11 (ja) → 4 (zh-Hant)",
            "forms": "PokeAPI pokemon_form_names language_id 4; newer メガ names are 超級 + species",
            "sets": "TCGdex ja set titles joined to asia.pokemon-card.com zh-cmn-Hant-HK by set code",
        },
        "counts": counts,
        **{name: _sorted(table) for name, table in groups.items()},
        "rarity_labels": _sorted(_RARITY_LABELS),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pokeapi-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.pokeapi_dir:
        species_csv = (args.pokeapi_dir / "pokemon_species_names.csv").read_text(encoding="utf-8")
        forms_csv = (args.pokeapi_dir / "pokemon_form_names.csv").read_text(encoding="utf-8")
    else:
        species_csv = _download(_SPECIES_URL)
        forms_csv = _download(_FORMS_URL)
    payload = build(species_csv, forms_csv)
    _OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["examples"] = _examples()
    _OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = payload["counts"]
    print(f"wrote {_OUT}")
    print(counts)


if __name__ == "__main__":
    main()
