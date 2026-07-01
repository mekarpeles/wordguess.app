import pytest

from game.engine import Player, Room, ROUND_TIME_LIMIT_SECONDS


class FakeClock:
    """A controllable clock for deterministic timer tests -- no real sleeping."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_players():
    a = Player(sid="sidA", name="Alice", native_lang="en", target_lang="fr", level="beginner")
    b = Player(sid="sidB", name="Bob", native_lang="fr", target_lang="en", level="beginner")
    return a, b


def make_room(clock):
    room = Room(code="ABCD", clock=clock)
    a, b = make_players()
    room.add_player(a)
    room.add_player(b)
    room.start_round()
    return room


def test_time_remaining_is_full_at_round_start():
    clock = FakeClock()
    room = make_room(clock)
    assert room.time_remaining() == ROUND_TIME_LIMIT_SECONDS


def test_time_remaining_decreases_as_clock_advances():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(30)
    assert room.time_remaining() == ROUND_TIME_LIMIT_SECONDS - 30


def test_time_remaining_never_goes_negative():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(ROUND_TIME_LIMIT_SECONDS + 500)
    assert room.time_remaining() == 0


def test_is_round_timed_out_false_before_limit():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(ROUND_TIME_LIMIT_SECONDS - 1)
    assert room.is_round_timed_out() is False


def test_is_round_timed_out_true_after_limit():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(ROUND_TIME_LIMIT_SECONDS + 1)
    assert room.is_round_timed_out() is True


def test_expire_round_if_timed_out_returns_none_when_not_timed_out():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(5)
    assert room.expire_round_if_timed_out() is None
    assert room.round.status == "active"


def test_expire_round_if_timed_out_marks_lost_and_reveals_word():
    clock = FakeClock()
    room = make_room(clock)
    word_before = room.round.word
    clock.advance(ROUND_TIME_LIMIT_SECONDS + 1)
    result = room.expire_round_if_timed_out()
    assert result is not None
    assert result["correct"] is False
    assert result["lost"] is True
    assert result["timed_out"] is True
    assert result["word"] == word_before
    assert room.round.status == "lost"


def test_expire_round_if_timed_out_is_noop_after_round_already_won():
    clock = FakeClock()
    room = make_room(clock)
    answer = room.round.word["translations"]["en"]
    room.submit_guess("sidA", answer)  # Alice wins immediately
    clock.advance(ROUND_TIME_LIMIT_SECONDS + 1)
    assert room.expire_round_if_timed_out() is None


def test_new_round_resets_the_timer():
    clock = FakeClock()
    room = make_room(clock)
    clock.advance(ROUND_TIME_LIMIT_SECONDS - 1)
    answer = room.round.word["translations"]["en"]
    room.submit_guess("sidA", answer)
    room.next_round()
    assert room.time_remaining() == ROUND_TIME_LIMIT_SECONDS


def test_submit_guess_after_timeout_raises_no_active_round():
    from game.errors import NoActiveRoundError

    clock = FakeClock()
    room = make_room(clock)
    clock.advance(ROUND_TIME_LIMIT_SECONDS + 1)
    room.expire_round_if_timed_out()
    with pytest.raises(NoActiveRoundError):
        room.submit_guess("sidA", "anything")
