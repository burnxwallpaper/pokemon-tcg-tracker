"""Load the Traditional Chinese JP→ZH name map and apply it.

`data/name_zh_map.json` is the dictionary. `translate()` walks each title
left to right and replaces the longest matching key, so ミュウツー stays
超夢 and メガニウム is not read as 超級.

`rarity_labels` is an exact-code lookup. Printed codes such as SAR stay
in titles.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MAP_PATH = _ROOT / "data" / "name_zh_map.json"
_KANA = re.compile(r"[ぁ-んァ-ヶー]")
_POSSESSIVE_NO = re.compile(r"(?<![ぁ-んァ-ヶー])の(?![ぁ-んァ-ヶー])")
_MEGA_M = re.compile(r"(?<![A-Za-z])M(?=[\u4e00-\u9fff])")


def map_path() -> Path:
    return _MAP_PATH


@lru_cache(maxsize=1)
def load_map() -> dict[str, object]:
    raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("name_zh_map.json must be an object")
    return raw


def _group(data: dict[str, object], name: str) -> dict[str, str]:
    raw = data.get(name, {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            out[key] = value
    return out


@lru_cache(maxsize=1)
def _compiled() -> tuple[dict[str, str], tuple[str, ...]]:
    data = load_map()
    groups = data.get("replace_groups")
    if not isinstance(groups, list):
        raise ValueError("name_zh_map.json replace_groups must be a list")
    table: dict[str, str] = {}
    for name in reversed(groups):
        if isinstance(name, str):
            table.update(_group(data, name))
    keys = tuple(sorted(table, key=len, reverse=True))
    return table, keys


def replacement_table() -> dict[str, str]:
    """Merged replace groups. Earlier groups in `replace_groups` win ties."""
    return dict(_compiled()[0])


def translate(text: str) -> str:
    """Japanese card or product title → Traditional Chinese (HK/TW)."""
    if not text:
        return text
    table, keys = _compiled()
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        hit = ""
        for key in keys:
            if text.startswith(key, i):
                hit = key
                break
        if hit:
            out.append(table[hit])
            i += len(hit)
        else:
            out.append(text[i])
            i += 1
    translated = _POSSESSIVE_NO.sub("的", "".join(out))
    return _MEGA_M.sub("超級", translated)


def rarity_label(code: str) -> str | None:
    """Exact rarity code → Traditional Chinese gloss. Not used by translate()."""
    labels = _group(load_map(), "rarity_labels")
    return labels.get(code)


def has_kana(text: str) -> bool:
    return _KANA.search(text) is not None


def translate_or_keep(text: str) -> tuple[str, str]:
    """Translate, or return the original when kana would still show.

    Status is ``zh`` or ``fallback``. A partial mix is not returned.
    """
    if not text:
        return text, "zh"
    translated = translate(text)
    if has_kana(translated):
        return text, "fallback"
    return translated, "zh"


def clear_cache() -> None:
    load_map.cache_clear()
    _compiled.cache_clear()
