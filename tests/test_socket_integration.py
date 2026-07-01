import pytest

from app import create_app


@pytest.fixture
def game_app():
    """A fresh Flask app + socketio instance with its own isolated room registry."""
    flask_app, socketio = create_app()
    flask_app.config["TESTING"] = True
    return flask_app, socketio


@pytest.fixture
def two_clients(game_app):
    """Two connected socketio test clients sharing one fresh app/registry."""
    flask_app, socketio = game_app
    client_a = socketio.test_client(flask_app)
    client_b = socketio.test_client(flask_app)
    yield client_a, client_b
    for client in (client_a, client_b):
        if client.is_connected():
            client.disconnect()


def _drain(client):
    # flask_socketio's get_received() clears the client's queue on every call,
    # so repeated calls silently discard events that don't match the name a
    # caller happens to be looking for right now. Keep a running log per
    # client instead so earlier events remain queryable later.
    log = getattr(client, "_test_log", None)
    if log is None:
        log = []
        client._test_log = log
    log.extend(client.get_received())
    return log


def _events(client, name):
    return [e for e in _drain(client) if e["name"] == name]


def _last(client, name):
    matches = _events(client, name)
    assert matches, f"expected at least one {name!r} event, got none"
    return matches[-1]["args"][0]


ALICE_PROFILE = {"name": "Alice", "native_lang": "en", "target_lang": "fr", "level": "beginner"}
BOB_PROFILE = {"name": "Bob", "native_lang": "fr", "target_lang": "en", "level": "beginner"}


def test_create_and_join_room_starts_round_for_both(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]

    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    # both players should receive a round_started event with a role
    alice_round = _last(alice, "round_started")
    bob_round = _last(bob, "round_started")
    roles = {alice_round["role"], bob_round["role"]}
    assert roles == {"guesser", "prompter"}
    # the guesser is player 1 (Alice), learning French
    assert alice_round["role"] == "guesser"
    assert alice_round["target_lang"] == "fr"
    # only the prompter's payload contains the secret word
    assert "secret_word" not in alice_round
    assert bob_round["role"] == "prompter"
    assert "secret_word" in bob_round


def test_join_unknown_room_returns_error(two_clients):
    alice, bob = two_clients
    alice.emit("join_room", {**ALICE_PROFILE, "code": "ZZZZ"})
    err = _last(alice, "error")
    assert "not found" in err["message"]
    # Regression: server-side error replies must target only the requesting
    # client (via to=request.sid), not broadcast to every connected socket.
    assert _events(bob, "error") == []


def test_list_open_games_returns_strict_mutual_matches(game_app):
    flask_app, socketio = game_app
    alice = socketio.test_client(flask_app)
    alice.emit("create_room", ALICE_PROFILE)  # en native / fr target
    code = _last(alice, "joined")["code"]

    seeker = socketio.test_client(flask_app)
    seeker.emit("list_open_games", {"native_lang": "fr", "target_lang": "en"})
    games = _last(seeker, "open_games")["games"]
    assert games == [{"code": code, "host_name": "Alice", "level": "beginner"}]

    mismatched = socketio.test_client(flask_app)
    mismatched.emit("list_open_games", {"native_lang": "es", "target_lang": "zh"})
    assert _last(mismatched, "open_games")["games"] == []

    alice.disconnect()
    seeker.disconnect()
    mismatched.disconnect()


def test_list_open_games_excludes_full_rooms(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})  # room now full

    alice.emit("list_open_games", {"native_lang": "fr", "target_lang": "en"})
    assert _last(alice, "open_games")["games"] == []


def test_third_player_rejected(game_app, two_clients):
    flask_app, socketio = game_app
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    carol = socketio.test_client(flask_app)
    carol.emit("join_room", {"name": "Carol", "native_lang": "en", "target_lang": "fr", "code": code})
    err = _last(carol, "error")
    assert "full" in err["message"].lower()
    # Regression: the "room full" error must not be broadcast to the
    # players already in the room.
    assert _events(alice, "error") == []
    assert _events(bob, "error") == []
    carol.disconnect()


def test_hint_with_taboo_word_is_rejected_and_not_broadcast(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob_round = _last(bob, "round_started")
    secret = bob_round["secret_word"]

    bob.emit("send_hint", {"text": f"Le mot ressemble a {secret}"})
    rejection = _last(bob, "hint_rejected")
    assert "taboo" in rejection["message"].lower() or "secret" in rejection["message"].lower()
    # alice must NOT have received a hint broadcast
    assert _events(alice, "hint") == []


def test_valid_hint_is_broadcast_to_both_players(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob.emit("send_hint", {"text": "c'est très commun dans la cuisine"})
    hint_for_alice = _last(alice, "hint")
    hint_for_bob = _last(bob, "hint")
    assert hint_for_alice["text"] == "c'est très commun dans la cuisine"
    assert hint_for_bob["text"] == "c'est très commun dans la cuisine"
    assert hint_for_alice["from_name"] == "Bob"


def test_hint_broadcast_is_annotated_with_emoji_for_known_words(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob.emit("send_hint", {"text": "c'est rouge et rond"})
    hint_for_alice = _last(alice, "hint")
    assert "rouge 🔴" in hint_for_alice["text"]


def test_guesser_cannot_send_hint(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    alice.emit("send_hint", {"text": "some hint"})  # Alice is guesser
    err = _last(alice, "error")
    assert "prompter" in err["message"].lower()


def test_guesser_can_flag_difficult_clue_broadcast_to_both(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    alice.emit("flag_difficult")  # Alice is guesser
    flagged_for_alice = _last(alice, "difficulty_flagged")
    flagged_for_bob = _last(bob, "difficulty_flagged")
    assert flagged_for_alice["from_name"] == "Alice"
    assert flagged_for_bob["from_name"] == "Alice"


def test_prompter_cannot_flag_difficult_clue(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob.emit("flag_difficult")  # Bob is prompter
    err = _last(bob, "error")
    assert "guesser" in err["message"].lower()


def test_guessing_the_target_language_word_flags_wrong_language(game_app):
    # Regression for a real playtest report: guesser answered with the
    # target-language word itself (what the prompter is hinting at) instead
    # of translating it into their own native language, and only saw a
    # generic "not quite" with no explanation.
    #
    # Several real wordbank entries are spelled identically (or near-
    # identically) in en/fr (e.g. "table", "justice", "silence") -- if one
    # of those were drawn, repeating the target word IS the correct
    # native-language answer too, which would coincidentally win the round
    # instead of triggering the wrong_language flag. Retry with a fresh
    # room/word rather than asserting on a random draw.
    flask_app, socketio = game_app
    from game.wordbank import load_wordbank

    words = load_wordbank()

    for _ in range(20):
        alice = socketio.test_client(flask_app)
        bob = socketio.test_client(flask_app)
        alice.emit("create_room", ALICE_PROFILE)
        code = _last(alice, "joined")["code"]
        bob.emit("join_room", {**BOB_PROFILE, "code": code})
        bob_round = _last(bob, "round_started")
        secret = bob_round["secret_word"]
        match = next(w for w in words if w["translations"]["fr"] == secret)
        answer = match["translations"]["en"]

        if secret.lower() == answer.lower():
            alice.disconnect()
            bob.disconnect()
            continue

        alice.emit("send_guess", {"text": secret})
        guess_result = _last(alice, "guess_result")
        assert guess_result["correct"] is False
        assert guess_result["wrong_language"] is True
        assert guess_result["remaining"] == 9
        alice.disconnect()
        bob.disconnect()
        return

    pytest.fail("could not draw a non-cognate word in 20 attempts")
    assert guess_result["remaining"] == 9


def test_wrong_guess_then_correct_guess_awards_score_and_swaps_roles(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob_round = _last(bob, "round_started")
    word_id_lookup_secret = bob_round["secret_word"]

    alice.emit("send_guess", {"text": "definitely-wrong"})
    guess_result = _last(alice, "guess_result")
    assert guess_result["correct"] is False
    assert guess_result["remaining"] == 9

    # We don't know the English answer directly from the socket payload
    # (by design the guesser never sees it) — but we can recover it via the
    # word bank using the French secret word, since translations are 1:1.
    from game.wordbank import load_wordbank

    words = load_wordbank()
    match = next(w for w in words if w["translations"]["fr"] == word_id_lookup_secret)
    answer = match["translations"]["en"]

    alice.emit("send_guess", {"text": answer})
    result = _last(alice, "round_result")
    assert result["correct"] is True
    assert result["winner_name"] == "Alice"
    assert result["score_awarded"] == 9  # second attempt

    # roles should have swapped for the next round
    new_alice_round = _last(alice, "round_started")
    new_bob_round = _last(bob, "round_started")
    assert new_alice_round["role"] == "prompter"
    assert new_bob_round["role"] == "guesser"
    assert new_bob_round["target_lang"] == "en"


def test_ten_failed_guesses_loses_round_and_swaps_roles(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    for _ in range(10):
        alice.emit("send_guess", {"text": "definitely-wrong-guess"})

    result = _last(alice, "round_result")
    assert result["correct"] is False
    assert result["score_awarded"] == 0

    new_alice_round = _last(alice, "round_started")
    assert new_alice_round["role"] == "prompter"


def test_disconnect_notifies_remaining_player(two_clients):
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})

    bob.disconnect()
    _last(alice, "opponent_left")


def test_winning_guess_after_opponent_disconnects_does_not_crash(two_clients):
    # Regression: _finish_round_and_advance used to call room.next_round(),
    # which requires 2 players -- a guess submitted right after the
    # opponent disconnects (a real race) would raise RoomNotReadyError
    # inside the socket handler.
    alice, bob = two_clients
    alice.emit("create_room", ALICE_PROFILE)
    code = _last(alice, "joined")["code"]
    bob.emit("join_room", {**BOB_PROFILE, "code": code})
    bob_round = _last(bob, "round_started")
    secret = bob_round["secret_word"]
    rounds_started_before = len(_events(alice, "round_started"))
    bob.disconnect()

    from game.wordbank import load_wordbank

    words = load_wordbank()
    match = next(w for w in words if w["translations"]["fr"] == secret)
    answer = match["translations"]["en"]

    alice.emit("send_guess", {"text": answer})
    result = _last(alice, "round_result")
    assert result["correct"] is True
    # no new round should have started -- the opponent is gone
    assert len(_events(alice, "round_started")) == rounds_started_before
