import pytest

from game.engine import Player, Room, SCORE_TABLE, is_close_match, normalize_text, contains_taboo
from game.errors import (
    NoActiveRoundError,
    NotYourTurnError,
    RoomFullError,
    RoomNotReadyError,
    TabooViolationError,
)
from game.wordbank import WordBank


def make_players():
    # A learns French, native English. B learns English, native French.
    a = Player(sid="sidA", name="Alice", native_lang="en", target_lang="fr", level="beginner")
    b = Player(sid="sidB", name="Bob", native_lang="fr", target_lang="en", level="beginner")
    return a, b


# --- normalize / matching -------------------------------------------------

def test_normalize_strips_case_whitespace_punctuation_and_accents():
    assert normalize_text("  Pomme! ") == "pomme"
    assert normalize_text("Árbol?") == "arbol"


def test_is_close_match_exact():
    assert is_close_match("pomme", "pomme")
    assert is_close_match(" Pomme ", "pomme")


def test_is_close_match_tolerates_single_typo_on_longer_words():
    assert is_close_match("aple", "apple")  # missing letter
    assert is_close_match("pomme", "ponme")  # transposed-ish, distance 1


def test_is_close_match_rejects_wrong_word():
    assert not is_close_match("banana", "apple")


def test_is_close_match_no_fuzziness_for_short_words():
    # short words: even 1 edit changes meaning too much, require exact match
    assert not is_close_match("cat", "car")


# --- taboo enforcement -----------------------------------------------------

def test_contains_taboo_detects_exact_word_case_insensitive():
    assert contains_taboo("It tastes like a POMME to me", ["pomme"])


def test_contains_taboo_ignores_accents_and_punctuation():
    assert contains_taboo("un arbre, un ARBRE!", ["arbre"])


def test_contains_taboo_false_when_absent():
    assert not contains_taboo("It is round and red", ["pomme"])


# --- Room / round lifecycle -------------------------------------------------

def test_room_rejects_third_player():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    with pytest.raises(RoomFullError):
        room.add_player(Player(sid="sidC", name="C", native_lang="en", target_lang="fr", level="beginner"))


def test_start_round_requires_two_players():
    room = Room(code="ABCD")
    a, _ = make_players()
    room.add_player(a)
    with pytest.raises(RoomNotReadyError):
        room.start_round()


def test_start_round_assigns_guesser_and_prompter_by_target_language():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    # first guesser is players[0] (Alice), whose target is French
    assert round_.guesser_sid == a.sid
    assert round_.prompter_sid == b.sid
    assert round_.target_lang == "fr"
    assert round_.word["level"] == "beginner"


def test_submit_hint_rejects_non_prompter():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()
    with pytest.raises(NotYourTurnError):
        room.submit_hint(a.sid, "some hint")  # Alice is guesser, not prompter


def test_submit_hint_rejects_taboo_word_and_does_not_record_it():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    secret = round_.word["translations"]["fr"]
    with pytest.raises(TabooViolationError):
        room.submit_hint(b.sid, f"Le mot est {secret}")
    assert round_.hints == []


def test_submit_hint_records_valid_hint():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()
    hint = room.submit_hint(b.sid, "un fruit rouge ou vert")
    assert hint["text"] == "un fruit rouge ou vert"
    assert room.round.hints[-1] == hint


def test_submit_guess_rejects_non_guesser():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()
    with pytest.raises(NotYourTurnError):
        room.submit_guess(b.sid, "apple")  # Bob is prompter, not guesser


def test_submit_guess_correct_awards_max_score_on_first_try():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    answer = round_.word["translations"][a.native_lang]  # Alice answers in English
    result = room.submit_guess(a.sid, answer)
    assert result["correct"] is True
    assert result["score"] == SCORE_TABLE[0]
    assert a.score == SCORE_TABLE[0]
    assert room.round.status == "won"


def test_submit_guess_score_decreases_with_more_attempts():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    answer = round_.word["translations"][a.native_lang]
    for _ in range(3):
        room.submit_guess(a.sid, "definitely-wrong")
    result = room.submit_guess(a.sid, answer)
    assert result["correct"] is True
    assert result["score"] == SCORE_TABLE[3]  # 4th attempt
    assert a.score == SCORE_TABLE[3]


def test_submit_guess_flags_wrong_language_when_guesser_repeats_target_word():
    # Regression: a real playtester guessed the target-language word itself
    # ("vecino") instead of translating it into their native language
    # ("neighbor"), got a generic "not quite", and had no idea why. The
    # engine should still mark it incorrect (native-language-only guessing
    # is an intentional design choice) but flag *why* so the UI can explain.
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    target_word = round_.word["translations"][round_.target_lang]

    result = room.submit_guess(a.sid, target_word)

    assert result["correct"] is False
    assert result["lost"] is False
    assert result["wrong_language"] is True
    assert result["remaining"] == 9
    # it still counts as a used attempt
    assert room.round.guesses_used == 1


def test_submit_guess_wrong_language_flag_is_false_for_an_unrelated_wrong_guess():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()

    result = room.submit_guess(a.sid, "definitely-unrelated")

    assert result["correct"] is False
    assert result["wrong_language"] is False


def test_submit_guess_loses_after_ten_wrong_guesses():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()
    result = None
    for _ in range(10):
        result = room.submit_guess(a.sid, "definitely-wrong")
    assert result["correct"] is False
    assert result["lost"] is True
    assert room.round.status == "lost"
    assert a.score == 0


def test_submit_guess_after_round_over_raises():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    answer = round_.word["translations"][a.native_lang]
    room.submit_guess(a.sid, answer)
    with pytest.raises(NoActiveRoundError):
        room.submit_guess(a.sid, answer)


def test_roles_swap_after_round_and_next_word_differs():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round1 = room.start_round()
    answer = round1.word["translations"][a.native_lang]
    room.submit_guess(a.sid, answer)

    round2 = room.next_round()
    assert round2.guesser_sid == b.sid
    assert round2.prompter_sid == a.sid
    assert round2.target_lang == "en"
    assert round2.word["id"] != round1.word["id"]


def test_recent_words_not_immediately_repeated_across_many_rounds():
    room = Room(code="ABCD")
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    seen_ids = [round_.word["id"]]
    for _ in range(5):
        answer = room.round.word["translations"][room.current_guesser().native_lang]
        room.submit_guess(room.round.guesser_sid, answer)
        round_ = room.next_round()
        seen_ids.append(round_.word["id"])
    # no immediate repeat of the word just used
    for prev, nxt in zip(seen_ids, seen_ids[1:]):
        assert prev != nxt


def test_start_round_recovers_when_word_pool_exhausted_by_history():
    # Only 2 words exist at this level; recent_history exclusion would
    # normally exhaust the pool on the 3rd round. The room should recover
    # by forgetting history instead of raising NoWordsAvailableError.
    tiny_bank = WordBank(
        [
            {"id": "one", "level": "beginner", "translations": {"en": "one", "fr": "un", "es": "uno", "zh": "一"}},
            {"id": "two", "level": "beginner", "translations": {"en": "two", "fr": "deux", "es": "dos", "zh": "二"}},
        ]
    )
    room = Room(code="ABCD", wordbank=tiny_bank, recent_history=8)
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    round_ = room.start_round()
    for _ in range(4):
        answer = room.round.word["translations"][room.current_guesser().native_lang]
        room.submit_guess(room.round.guesser_sid, answer)
        round_ = room.next_round()
    assert round_.word["id"] in {"one", "two"}
