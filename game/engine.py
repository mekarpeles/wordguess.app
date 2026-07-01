import re
import unicodedata
from dataclasses import dataclass, field

from game.errors import (
    NoActiveRoundError,
    NoWordsAvailableError,
    NotYourTurnError,
    RoomFullError,
    RoomNotReadyError,
    TabooViolationError,
)
from game.wordbank import WordBank, load_wordbank

MAX_GUESSES = 10
SCORE_TABLE = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
_FUZZY_MIN_LEN = 5
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _PUNCT_RE.sub("", text)
    return text.strip()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def is_close_match(guess: str, answer: str) -> bool:
    g, a = normalize_text(guess), normalize_text(answer)
    if g == a:
        return True
    if len(a) < _FUZZY_MIN_LEN:
        return False
    return _levenshtein(g, a) <= 1


def contains_taboo(text: str, taboo_words: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(word) in normalized for word in taboo_words if word)


@dataclass
class Player:
    sid: str
    name: str
    native_lang: str
    target_lang: str
    level: str
    score: int = 0


@dataclass
class Round:
    word: dict
    target_lang: str
    guesser_sid: str
    prompter_sid: str
    guesses_used: int = 0
    hints: list = field(default_factory=list)
    guesses: list = field(default_factory=list)
    status: str = "active"  # active | won | lost


class Room:
    def __init__(self, code: str, wordbank: WordBank | None = None, recent_history: int = 8):
        self.code = code
        self.wordbank = wordbank or WordBank(load_wordbank())
        self.players: dict[str, Player] = {}
        self.player_order: list[str] = []
        self.guesser_idx = 0
        self.recent_word_ids: list[str] = []
        self._recent_history = recent_history
        self.round: Round | None = None

    def add_player(self, player: Player) -> None:
        if len(self.players) >= 2:
            raise RoomFullError(f"room {self.code} already has 2 players")
        self.players[player.sid] = player
        self.player_order.append(player.sid)

    def current_guesser(self) -> Player:
        return self.players[self.player_order[self.guesser_idx]]

    def current_prompter(self) -> Player:
        return self.players[self.player_order[1 - self.guesser_idx]]

    def start_round(self) -> Round:
        if len(self.players) < 2:
            raise RoomNotReadyError(f"room {self.code} needs 2 players to start")
        guesser = self.current_guesser()
        prompter = self.current_prompter()
        try:
            word = self.wordbank.pick_word(
                level=guesser.level, exclude_ids=set(self.recent_word_ids)
            )
        except NoWordsAvailableError:
            # Word pool for this level is exhausted by recent-history exclusion.
            # Forget history and retry rather than crashing a long-running game.
            self.recent_word_ids.clear()
            word = self.wordbank.pick_word(level=guesser.level, exclude_ids=set())
        self._remember_word(word["id"])
        self.round = Round(
            word=word,
            target_lang=guesser.target_lang,
            guesser_sid=guesser.sid,
            prompter_sid=prompter.sid,
        )
        return self.round

    def next_round(self) -> Round:
        self.guesser_idx = 1 - self.guesser_idx
        return self.start_round()

    def _remember_word(self, word_id: str) -> None:
        self.recent_word_ids.append(word_id)
        if len(self.recent_word_ids) > self._recent_history:
            self.recent_word_ids.pop(0)

    def _require_active_round(self) -> Round:
        if self.round is None or self.round.status != "active":
            raise NoActiveRoundError(f"room {self.code} has no active round")
        return self.round

    def _taboo_words(self, round_: Round) -> list[str]:
        guesser = self.players[round_.guesser_sid]
        word = round_.word
        return [word["translations"][round_.target_lang], word["translations"][guesser.native_lang]]

    def submit_hint(self, sid: str, text: str) -> dict:
        round_ = self._require_active_round()
        if sid != round_.prompter_sid:
            raise NotYourTurnError("only the prompter may send hints")
        if contains_taboo(text, self._taboo_words(round_)):
            raise TabooViolationError("hint may not contain the secret word or its translation")
        hint = {"sid": sid, "text": text}
        round_.hints.append(hint)
        return hint

    def flag_difficult(self, sid: str) -> None:
        round_ = self._require_active_round()
        if sid != round_.guesser_sid:
            raise NotYourTurnError("only the guesser may flag a clue as too difficult")

    def submit_guess(self, sid: str, text: str) -> dict:
        round_ = self._require_active_round()
        if sid != round_.guesser_sid:
            raise NotYourTurnError("only the guesser may submit guesses")
        round_.guesses_used += 1
        round_.guesses.append({"sid": sid, "text": text})

        guesser = self.players[sid]
        answer = round_.word["translations"][guesser.native_lang]
        correct = is_close_match(text, answer)

        if correct:
            round_.status = "won"
            score = SCORE_TABLE[round_.guesses_used - 1]
            guesser.score += score
            return {
                "correct": True,
                "lost": False,
                "score": score,
                "word": round_.word,
                "guesses_used": round_.guesses_used,
            }

        # Real playtesting showed guessers naturally repeat the target-
        # language word itself (what they read in the hints) instead of
        # translating it into their own native language, which this game
        # intentionally requires. Flag that specific mix-up so the UI can
        # explain it, rather than a generic "not quite".
        target_word = round_.word["translations"][round_.target_lang]
        wrong_language = is_close_match(text, target_word)

        if round_.guesses_used >= MAX_GUESSES:
            round_.status = "lost"
            return {
                "correct": False,
                "lost": True,
                "score": 0,
                "word": round_.word,
                "guesses_used": round_.guesses_used,
                "wrong_language": wrong_language,
            }

        return {
            "correct": False,
            "lost": False,
            "score": 0,
            "remaining": MAX_GUESSES - round_.guesses_used,
            "wrong_language": wrong_language,
        }
