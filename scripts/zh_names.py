"""Traditional Chinese display names for Japanese TCG titles.

Species names are the official zh-Hant names from PokeAPI (language id 4).
Trainer cards and set titles follow the HK/TW Pokémon TCG names on
asia.pokemon-card.com. Search keywords are not touched.

If kana remains after known replacements, the original Japanese title is
kept and marked fallback so a partial mix is never shown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SPECIES_PATH = _ROOT / "data" / "pokemon_ja_zhtw.json"
# Katakana middle dot (・) is also used in Traditional Chinese names, so it is not leftover Japanese.
_KANA = re.compile(r"[\u3040-\u30fa\u30fc-\u30ff]")
_KANA_GROUP = re.compile(r"[（(][^（）()]*" + _KANA.pattern + r"[^（）()]*[）)]")

# Longer keys are applied first. These are official HK/TW card or product titles,
# plus place-name promos whose Japanese label is not a species name.
_PHRASES: dict[str, str] = {
    "30th CELEBRATION プレミアムデッキセット エーフィ・ブラッキー": "30th CELEBRATION 高級牌組組合 太陽伊布・月亮伊布",
    "ポケモンワールドチャンピオンシップス2023横浜": "寶可夢世界錦標賽2023橫濱",
    "スカーレット&バイオレット": "朱&紫",
    "ソード & シールド": "劍&盾",
    "ソード&シールド": "劍&盾",
    "ポケモンカードゲームMEGA": "寶可夢卡牌遊戲MEGA",
    "ポケモンカードゲーム Classic": "寶可夢卡牌遊戲 Classic",
    "ポケモンカードゲーム": "寶可夢卡牌遊戲",
    "スペシャルデッキセットex": "特別牌組組合ex",
    "プレミアムデッキセット": "高級牌組組合",
    "スタートデッキ100": "起始牌組100",
    "プロモカードパック": "特典卡包",
    "プロモーションカード": "特典卡",
    "ポケモン切手BOX": "寶可夢郵票BOX",
    "マスターボールミラー": "大師球鏡",
    "モンスターボールミラー": "精靈球鏡",
    "強化拡張パック": "強化擴充包",
    "ハイクラスパック": "高級擴充包",
    "コンセプトパック": "概念包",
    "拡張パック": "擴充包",
    "25th アニバーサリーコレクション": "25週年收藏款",
    "25th アニバーサリー コレクション": "25週年收藏款",
    "25th アニバーサリー": "25週年紀念",
    "アニバーサリーコレクション": "週年收藏款",
    "アニバーサリー": "週年紀念",
    "コレクション": "收藏",
    "25th ANNIVERSARY edition": "25th ANNIVERSARY edition",
    "25th ANNIVERSARY COLLECTION": "25週年收藏款",
    "ゴールデンボックス": "黃金盒",
    "特別セット": "特別組合",
    "スペシャルBOX": "特別BOX",
    "構築デッキ": "構築牌組",
    "記念デッキ": "紀念牌組",
    "リーリエの決心": "莉莉艾的決意",
    "アセロラのいたずら": "阿塞蘿拉的惡作劇",
    "エリカの招待": "莉佳的招待",
    "ヒガナの信頼": "希嘉娜的信賴",
    "メイのはげまし": "鳴依的勉勵",
    "ルチアのアピール": "露琪亞的吸引力",
    "カミツレのきらめき": "小菊兒的閃耀",
    "ロケット団の栄光": "火箭隊的榮耀",
    "ロケット団参上!": "火箭隊來襲！",
    "ロケット団参上": "火箭隊來襲",
    "ロケット団の": "火箭隊的",
    "シロナの覇気": "竹蘭的霸氣",
    "ヒビキのホウオウ": "阿響的鳳王",
    "熱風アリーナ": "熱風競技場",
    "ナイトワンダラー": "黑夜漫遊者",
    "楽園ドラゴーナ": "樂園騰龍",
    "ステラミラクル": "星星奇跡",
    "お誕生日ピカチュウ": "生日皮卡丘",
    "_のピカチュウ": "生日皮卡丘",
    "海で遊ぶピカチュウ": "海邊玩耍皮卡丘",
    "漫才ごっこピカチュウ": "漫才表演皮卡丘",
    "カナザワのピカチュウ": "金澤的皮卡丘",
    "トウホクのピカチュウ": "東北的皮卡丘",
    "ヒロシマのピカチュウ": "廣島的皮卡丘",
    "フクオカのピカチュウ": "福岡的皮卡丘",
    "ヨコハマのピカチュウ": "橫濱的皮卡丘",
    "サトシのピカチュウ": "小智的皮卡丘",
    "レッドのピカチュウ": "赤紅的皮卡丘",
    "名探偵ピカチュウ": "名偵探皮卡丘",
    "ゴッホピカチュウ": "梵高皮卡丘",
    "ふしぎなしっぽ": "神秘尾巴",
    "ひかるセレビィ": "閃耀時拉比",
    "なみのりピカチュウ": "衝浪皮卡丘",
    "そらをとぶピカチュウ": "飛行皮卡丘",
    "わるいギャラドス": "邪惡暴鯉龍",
    "オリジンパルキア": "起源帕路奇亞",
    "オーガポン いしずえのめん": "厄鬼椪 礎石面具",
    "オーガポン いどのめん": "厄鬼椪 水井面具",
    "オーガポン かまどのめん": "厄鬼椪 火灶面具",
    "メガドリームex": "超級進化夢想ex",
    "MEGAドリームex": "超級進化夢想ex",
    "テラスタルフェスex": "太晶慶典ex",
    "シャイニートレジャーex": "閃色寶藏ex",
    "シャイニートレジャー": "閃色寶藏ex",
    "シャイニースターV": "閃色明星V",
    "VSTARユニバース": "天地萬物VSTAR",
    "VMAXクライマックス": "VMAX絕群壓軸",
    "イーブイヒーローズ": "伊布英雄",
    "トリプレットビート": "三連音爆",
    "レイジングサーフ": "激狂駭浪",
    "スノーハザード": "冰雪險境",
    "クレイバースト": "碟旋暴擊",
    "ワイルドフォース": "狂野之力",
    "未来の一閃": "未來閃光",
    "ホワイトフレア": "純白閃焰",
    "変幻の仮面": "變幻假面",
    "超電ブレイカー": "超電突圍",
    "蒼空ストリーム": "蒼空烈流",
    "スターバース": "星星誕生",
    "ロストアビス": "迷途深淵",
    "パラダイムトリガー": "思維激盪",
    "クリムゾンヘイズ": "緋紅薄霧",
    "ポケモンカード151": "寶可夢卡牌151",
    "バトルパートナーズ": "對戰搭檔",
    "ブラックボルト": "漆黑伏特",
    "黒炎の支配者": "黯焰支配者",
    "ダークファンタズマ": "黑暗亡靈",
    "白熱のアルカナ": "白熱奧秘",
    "バイオレットex": "紫ex",
    "メガシンフォニア": "超級交響樂",
    "メガブレイブ": "超級勇氣",
    "ムニキスゼロ": "虛無歸零",
    "ニンジャスピナー": "忍者飛旋",
    "ストームエメラルダ": "綠寶石風暴",
    "インフェルノX": "烈獄狂火X",
    "アビスアイ": "深淵之瞳",
    "ドリームリーグ": "夢之聯盟",
    "タッグオールスターズ": "聯手明星大集合",
    "スペースジャグラー": "空間魔術師",
    "フュージョンアーツ": "匯流藝術",
    "仰天のボルテッカー": "驚天伏特攻擊",
    "フルイラスト": "全圖",
    "ビニールなし": "無膠套",
    "マークあり": "有印記",
    "マクドナルド": "麥當勞",
    "ハッピーセット": "開心樂園餐",
    "コロコロコミック": "快樂快樂",
    "月号": "月號",
    "付録": "附錄",
    "未来": "未來",
    "ボックス": "盒",
    "未開封": "未開封",
    "プロモ": "特典",
    "仕様": "樣式",
    "ミラー": "鏡",
    "ノーマル": "普通",
}

_TRAINERS: dict[str, str] = {
    "ナンジャモ": "奇樹",
    "リーリエ": "莉莉艾",
    "アセロラ": "阿塞蘿拉",
    "カミツレ": "小菊兒",
    "ヒガナ": "希嘉娜",
    "ヒカリ": "小光",
    "スグリ": "烏栗",
    "ゼイユ": "丹瑜",
    "オリーヴ": "奧利薇",
    "ルチア": "露琪亞",
    "ルリナ": "露璃娜",
    "エリカ": "莉佳",
    "ミモザ": "米莫莎",
    "セレナ": "莎莉娜",
    "マリィ": "瑪俐",
    "カナリィ": "卡娜莉",
    "メロン": "美蓉",
    "ルリナ": "露璃娜",
    "オリーヴ": "奧利薇",
    "スグリ": "烏栗",
    "ゼイユ": "丹瑜",
    "ヒカリ": "小光",
    "サトシ": "小智",
    "レッド": "赤紅",
    "メイ": "鳴依",
}

_PREFIXES: dict[str, str] = {
    "メガ": "超級",
    "アローラ": "阿羅拉",
    "ガラル": "伽勒爾",
    "ヒスイ": "洗翠",
    "オリジン": "起源",
    "ひかる": "閃耀",
    "なみのり": "衝浪",
    "そらをとぶ": "飛行",
    "名探偵": "名偵探",
    "ゴッホ": "梵高",
    "わるい": "邪惡",
}


def _species() -> dict[str, str]:
    raw = json.loads(_SPECIES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            out[key] = value
    return out


_SPECIES = _species()


def _apply(text: str, table: dict[str, str]) -> str:
    for src, dst in sorted(table.items(), key=lambda item: len(item[0]), reverse=True):
        if src in text:
            text = text.replace(src, dst)
    return text


def _drop_repeat_groups(text: str) -> str:
    """Drop a parenthetical that only repeats a name already in the title."""

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        outside = text[: match.start()] + text[match.end() :]
        if inner and inner in outside:
            return ""
        return match.group(0)

    return re.sub(r"[（(]([^（）()]*)[）)]", repl, text)


def _drop_kana_groups(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _KANA_GROUP.sub("", text)
    return text


def display_name_zh(name_jp: str) -> tuple[str, str]:
    """Return (display_name, status) where status is 'zh' or 'fallback'."""
    raw = str(name_jp or "").strip()
    if not raw:
        return raw, "fallback"
    if not _KANA.search(raw):
        return raw, "zh"

    text = raw.replace("＆", "&").replace("　", " ")
    text = re.sub(r"\s*-\s*¥\s*$", "", text)
    text = _apply(text, _PHRASES)
    text = _apply(text, _SPECIES)
    text = _apply(text, _PREFIXES)
    text = _apply(text, _TRAINERS)
    text = text.replace("の", "的")
    text = re.sub(r":\s*1ED\b", " 初版", text)
    text = re.sub(r"(?<![A-Za-z0-9])1ED\b", "初版", text)
    text = _drop_kana_groups(text)
    text = _drop_repeat_groups(text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([）)])", r"\1", text)
    text = re.sub(r"([（(])\s+", r"\1", text)
    text = text.replace("BOX 未開封", "BOX（未開封）").strip(" \t-·")
    if _KANA.search(text):
        return raw, "fallback"
    return text, "zh"


def stamp_display_name(row: dict) -> dict:
    """Set name_zh from name_jp. Leaves name_jp and search fields unchanged.

    A failed translation does not replace an existing Traditional Chinese title.
    """
    source = str(row.get("name_jp") or row.get("name_zh") or "")
    existing = str(row.get("name_zh") or "")
    zh_name, status = display_name_zh(source)
    if status == "fallback" and existing and not _KANA.search(existing):
        row["name_zh"] = existing
        row.pop("name_zh_fallback", None)
        return row
    row["name_zh"] = zh_name
    if status == "fallback":
        row["name_zh_fallback"] = True
    else:
        row.pop("name_zh_fallback", None)
    return row


def _stamp_collection(rows: object) -> tuple[int, int]:
    zh_n = 0
    fallback_n = 0
    if not isinstance(rows, list):
        return zh_n, fallback_n
    for row in rows:
        if not isinstance(row, dict) or "name_zh" not in row:
            continue
        before = row.get("name_zh")
        stamp_display_name(row)
        if row.get("name_zh_fallback"):
            fallback_n += 1
        elif row.get("name_zh") != before or not _KANA.search(str(before or "")):
            zh_n += 1
    return zh_n, fallback_n


def refresh_saved_names(root: Path | None = None) -> dict[str, int]:
    """Rewrite display names in latest.json and the catalog. Prices stay put."""
    base = root or _ROOT.parent
    latest_path = base / "data" / "latest.json"
    catalog_path = base / "data" / "catalog" / "watchlist.json"
    catalog_dir = base / "data" / "catalog"

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    zh_n, fallback_n = _stamp_collection(latest.get("items"))
    sections = latest.get("sections")
    if isinstance(sections, dict):
        for rows in sections.values():
            _stamp_collection(rows)
    latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    watch = json.loads(catalog_path.read_text(encoding="utf-8"))
    _stamp_collection(watch.get("items"))
    catalog_path.write_text(json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    catalog_files = 0
    for path in catalog_dir.glob("*.json"):
        if path.name == "watchlist.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and "name_zh" in doc:
            stamp_display_name(doc)
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            catalog_files += 1

    return {
        "zh": zh_n,
        "fallback": fallback_n,
        "catalog_files": catalog_files,
    }


if __name__ == "__main__":
    stats = refresh_saved_names()
    print(stats)
