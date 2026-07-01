import json
import random
from pathlib import Path

from game.errors import NoWordsAvailableError

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "wordbank.json"


def load_wordbank(path: Path = DATA_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["words"]


class WordBank:
    def __init__(self, words: list[dict]):
        self._words = words

    def pick_word(self, level: str, exclude_ids: set[str]) -> dict:
        candidates = [
            w for w in self._words if w["level"] == level and w["id"] not in exclude_ids
        ]
        if not candidates:
            raise NoWordsAvailableError(
                f"no words available for level={level!r} excluding {exclude_ids!r}"
            )
        return random.choice(candidates)
