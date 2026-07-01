import re

from game.engine import normalize_text
from game.wordbank import load_wordbank

# One emoji per wordbank concept (word id), not one per language --
# translations are reused from data/wordbank.json so the same emoji shows
# for "apple" (en), "pomme" (fr), "manzana" (es), "苹果" (zh) without
# duplicating the emoji string per language. Abstract words with no clear,
# unambiguous emoji are intentionally omitted -- a misleading emoji is
# worse than no emoji for a learning tool.
WORD_ID_EMOJI = {
    "apple": "🍎",
    "dog": "🐶",
    "cat": "🐱",
    "water": "💧",
    "house": "🏠",
    "sun": "☀️",
    "moon": "🌙",
    "book": "📖",
    "car": "🚗",
    "tree": "🌳",
    "bread": "🍞",
    "milk": "🥛",
    "friend": "🧑‍🤝‍🧑",
    "school": "🏫",
    "chair": "🪑",
    "fish": "🐟",
    "bird": "🐦",
    "rain": "🌧️",
    "fire": "🔥",
    "mountain": "⛰️",
    "journey": "🧳",
    "mirror": "🪞",
    "bridge": "🌉",
    "dream": "💭",
    "harvest": "🌾",
    "silence": "🤫",
    "promise": "🤝",
    "weather": "⛅",
    "freedom": "🕊️",
    "justice": "⚖️",
    "wisdom": "🦉",
}

# Common hint descriptors that aren't full wordbank entries (colors, sizes,
# etc). Same shape as a wordbank word -- one canonical concept with
# per-language translations -- so the emoji string isn't duplicated per
# language here either.
EXTRA_CONCEPTS = [
    {"emoji": "🔴", "translations": {"en": "red", "fr": "rouge", "es": "rojo", "zh": "红色"}},
    {"emoji": "🔵", "translations": {"en": "blue", "fr": "bleu", "es": "azul", "zh": "蓝色"}},
    {"emoji": "🟢", "translations": {"en": "green", "fr": "vert", "es": "verde", "zh": "绿色"}},
    {"emoji": "🟡", "translations": {"en": "yellow", "fr": "jaune", "es": "amarillo", "zh": "黄色"}},
    {"emoji": "⚫", "translations": {"en": "black", "fr": "noir", "es": "negro", "zh": "黑色"}},
    {"emoji": "⚪", "translations": {"en": "white", "fr": "blanc", "es": "blanco", "zh": "白色"}},
    {"emoji": "🐘", "translations": {"en": "big", "fr": "grand", "es": "grande", "zh": "大"}},
    {"emoji": "🐜", "translations": {"en": "small", "fr": "petit", "es": "pequeño", "zh": "小"}},
    {"emoji": "🥵", "translations": {"en": "hot", "fr": "chaud", "es": "caliente", "zh": "热"}},
    {"emoji": "🥶", "translations": {"en": "cold", "fr": "froid", "es": "frío", "zh": "冷"}},
    {"emoji": "🍬", "translations": {"en": "sweet", "fr": "sucré", "es": "dulce", "zh": "甜"}},
    {"emoji": "🍋", "translations": {"en": "sour", "fr": "aigre", "es": "agrio", "zh": "酸"}},
    {"emoji": "⚡", "translations": {"en": "fast", "fr": "rapide", "es": "rápido", "zh": "快"}},
    {"emoji": "🐢", "translations": {"en": "slow", "fr": "lent", "es": "lento", "zh": "慢"}},
    {"emoji": "😊", "translations": {"en": "happy", "fr": "heureux", "es": "feliz", "zh": "开心"}},
    {"emoji": "😢", "translations": {"en": "sad", "fr": "triste", "es": "triste", "zh": "伤心"}},
]

ALL_EMOJI = {*WORD_ID_EMOJI.values(), *(c["emoji"] for c in EXTRA_CONCEPTS)}

_TOKEN_RE = re.compile(r"(\w+|\W+)", re.UNICODE)


def _build_emoji_index() -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for word in load_wordbank():
        emoji = WORD_ID_EMOJI.get(word["id"])
        if not emoji:
            continue
        for lang, text in word["translations"].items():
            index.setdefault(lang, {})[normalize_text(text)] = emoji
    for concept in EXTRA_CONCEPTS:
        for lang, text in concept["translations"].items():
            index.setdefault(lang, {})[normalize_text(text)] = concept["emoji"]
    return index


EMOJI_INDEX = _build_emoji_index()


def annotate_hint(text: str, lang: str) -> str:
    lang_index = EMOJI_INDEX.get(lang)
    if not lang_index:
        return text
    parts = _TOKEN_RE.findall(text)
    out = []
    for part in parts:
        out.append(part)
        emoji = lang_index.get(normalize_text(part))
        if emoji:
            out.append(f" {emoji}")
    return "".join(out)
