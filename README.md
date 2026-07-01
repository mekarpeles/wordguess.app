# wordguess.app

A real-time, two-player language-learning guessing game. One player (the
**prompter**) sees a secret word and gives hints/synonyms *in that word's
language* without ever using the word itself. The other player (the
**guesser**) reads the hints and answers *in their own native language*
(translation-style, testing comprehension rather than production). Guess
correctly within 10 tries to score points; fail all 10 and the word is
revealed. Either way, roles swap for the next word so both players get equal
turns learning.

This document is the living source of truth for how the game works, how to
run it, and what we've learned building it — update it as you go, don't let
knowledge live only in chat history or PR descriptions.

## Status

MVP in active development on branch `two-player-realtime-game`. Not yet
merged to `main`. See open PR for review status.

## How the game works

- Each **account/profile** has: a name, a `native_lang` (confident language),
  a `target_lang` (language they're learning), and a `level`
  (beginner / intermediate / advanced) in the target language.
- Two players join the same **room** (4-letter code). Room state is
  in-memory only — no database, no persistence across server restart. This
  is intentional for MVP scope (see `AGENTS.md`/`pm` guidance: don't focus on
  scale).
- When both players are present, the server starts a round:
  - The **guesser** for round 1 is player 1 (join order). Their `target_lang`
    is the round's language.
  - The **prompter** is the other player. They're shown the secret word (in
    the round's target language) and must give hints/synonyms *in that
    language*, never using the secret word (or its translation into the
    guesser's native language — that would be an instant giveaway).
  - The **guesser** never sees the secret word. They read the prompter's
    hints and try to answer *in their own native language* — i.e., "what do
    you think this word means, in words you're fluent in?" This is a
    comprehension check, not a spelling/production check in the target
    language.
  - Guesses are lightly fuzzy-matched (Levenshtein distance ≤ 1, and only for
    answers ≥ 5 characters after normalization) so small typos don't cost a
    win. Short words require an exact match (e.g. "cat" vs "car" must not be
    treated as the same guess).
  - Up to 10 guesses per word. Correct guess earns
    `[10,9,8,7,6,5,4,3,2,1][attempt_number - 1]` points (fewer attempts =
    more points). 10 failed guesses = 0 points and the word is revealed.
  - **After every round (win or lose), roles swap** — the guesser becomes
    the prompter and vice versa, and the round's language switches to
    whichever player is now guessing. This is what makes the game a mutual
    exchange: both players spend roughly equal time in "learning" mode.
  - Words don't repeat immediately — the server tracks recent word IDs (last
    8) per room and excludes them when picking the next word, per level.

## Architecture

- **Backend**: Flask + Flask-SocketIO (`async_mode="threading"` — no
  eventlet/gevent needed for this scale; simpler to run in Docker and to
  test with `flask_socketio.test_client`).
- **Game logic** (`game/`) is pure Python, framework-agnostic, and fully
  unit-tested without any Flask/socket involvement:
  - `game/wordbank.py` — loads `data/wordbank.json`, picks a word by level
    excluding recent IDs.
  - `game/engine.py` — `Player`, `Round`, `Room` — the state machine for
    role assignment, hint taboo-checking, guess matching/scoring, and role
    swapping. No I/O, no sockets — this is what makes it fast/easy to test.
  - `game/errors.py` — typed exceptions the socket layer maps to
    client-facing error/rejection events.
- **Realtime layer** (`app.py`) is a thin adapter: translates Socket.IO
  events into `Room` method calls, and broadcasts results. It sends
  **different payloads to each role** (the prompter's socket gets the secret
  word; the guesser's does not) via `emit(..., to=sid)`.
- **Frontend** (`templates/`, `static/`) is intentionally minimal: vanilla
  JS + a locally vendored `socket.io.min.js` (no CDN dependency, so it works
  on a LAN with no internet — see Gotchas). No build step, no framework.
- **Word data** (`data/wordbank.json`) is a static, hand-curated list of ~44
  words across 3 levels with translations in `en`, `fr`, `es`, `zh`. No GPT
  calls, no external API — fully offline and deterministic (this matters for
  testability: the old GPT-based single-player prototype could not be
  meaningfully unit tested because behavior depended on a live model).

## Data model

`data/wordbank.json`:
```json
{"words": [
  {"id": "apple", "level": "beginner",
   "translations": {"en": "apple", "fr": "pomme", "es": "manzana", "zh": "苹果"}}
]}
```

Player profile (submitted on room create/join):
```json
{"name": "Alice", "native_lang": "en", "target_lang": "fr", "level": "beginner"}
```

## Running locally (no Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/ -v          # unit + socketio integration tests
python app.py                       # serves on http://0.0.0.0:5000
```

## Running in Docker

```bash
docker compose -p wordguess-two-player up -d --build web
# app is on http://localhost:5050 — reachable from other machines on the
# same LAN via http://<host-machine-lan-ip>:5050 (find your LAN IP with
# `ipconfig getifaddr en0` on macOS)

# run the test suite inside the same environment used for the runtime image:
docker compose -p wordguess-two-player run --rm web python -m pytest tests/ -v

# spin down when done (per pm/AGENTS.md multi-agent Docker policy):
docker compose -p wordguess-two-player down
```

Port 5050 (not 5000) is used deliberately — see Gotchas below.

To play across two computers on the same local network: one player opens
`http://<host-lan-ip>:5050`, fills in their profile, and clicks "Create
room". They share the 4-letter room code (or the full `/room/<code>` URL)
with the second player, who opens the same base URL on their own machine,
fills in their own profile, and enters the code to join.

## Definition of done: two-agent end-to-end verification

This is the concrete, checkable bar for calling the game "working," agreed
with Mek on 2026-06-30. It must be re-satisfied (not just re-asserted) after
any change to the socket protocol or frontend. All 12 numbered items must be
driven through the real UI in two real (Playwright) browser contexts against
a running instance (Docker or `python app.py`) — **not** via raw
`socketio.emit` calls from a script. Simulating the DOM interactions a human
would perform (click, type, click send) is the bar; API-level tests alone do
not satisfy this.

1. Two independent browser contexts connect to the running instance.
2. Player A fills the profile form (name, native lang, target lang, level)
   and clicks "Create Room" — sees a room code rendered in the DOM.
3. Player B fills their own (complementary) profile, enters that code, and
   clicks "Join Room" — sees a "joined" confirmation.
4. Both browsers transition to the game view automatically, no page reload.
5. Exactly one browser's DOM shows the secret word (prompter view); the
   other's DOM does not contain it anywhere (guesser view) — checked by
   reading rendered DOM content, not by inspecting network payloads.
6. The prompter types the secret word itself into the hint box and sends it
   — the UI shows a visible rejection in the prompter's own view, and the
   text never appears in the guesser's chat log.
7. The prompter sends a valid (non-taboo) hint — it appears in the guesser's
   chat log in real time, no refresh.
8. The guesser submits a deliberately wrong guess — both browsers show the
   guess in the chat log, and the guesser's "guesses remaining" counter
   decrements.
9. The guesser submits the correct answer (in their own native language) —
   both browsers show a round-result message with the score awarded, and
   the scoreboard updates in both browsers' DOM.
10. Roles visibly swap for round 2: the former guesser's DOM now shows a
    secret word (prompter view) and the former prompter's DOM now shows the
    guesser view — verified by re-reading the DOM, not assumed from step 9.
11. Loss path (separate run/scenario): the guesser submits 10 wrong guesses
    in a row — the UI reveals the word and roles still swap afterward.
12. No unhandled JavaScript console errors during the full sequence in
    either browser context.

Only when all of the above pass does the two-player game count as verified
end-to-end. This section should be updated (not deleted) if the protocol
changes in a way that changes what "correct" looks like.

## Testing strategy (TDD)

1. **Unit tests** (`tests/test_wordbank.py`, `tests/test_engine.py`) — pure
   game logic, no Flask/sockets. Written before implementation.
2. **Socket integration tests** (`tests/test_socket_integration.py`) — uses
   `flask_socketio.test_client` to simulate two connected clients through a
   full round (join, hint, taboo rejection, wrong guesses, correct guess,
   role swap) without a real browser.
3. **Playwright end-to-end test** (`tests_e2e/`) — two real browser contexts
   against a running instance (Docker or `python app.py`), driving the
   actual UI as two humans would. This is the final verification gate before
   calling anything "done" — automated API tests passing is not sufficient
   proof the game is playable.

Run everything:
```bash
docker compose run --rm web python -m pytest tests/ -v
```

## Known limitations (MVP scope, intentional)

- No accounts/persistence — profiles are re-entered each time you join a
  room; scores reset when the server restarts or the room empties.
- No language-detection validation on chat input — the UI labels which
  language to type in, but a player *could* type in the wrong language and
  the server won't catch it (taboo-word matching still works regardless).
- No matchmaking — players must share a room code manually. Works for LAN
  play with 2 known people; not a public matchmaking service.
- No reconnect/resume — if a player's browser refreshes mid-round, they
  rejoin as a new socket and the room treats them as absent (see Gotchas).

## Gotchas / things we learned building this

- **Vendor the Socket.IO client JS locally** (`static/js/socket.io.min.js`),
  don't load it from a CDN. LAN play may happen with no internet uplink on
  the host, and a CDN dependency would silently break the whole game with a
  blank page and no obvious error.
- **`async_mode="threading"` over eventlet/gevent**: avoids monkey-patching
  surprises in tests and in Docker; at MVP scale (2 players per room, a
  handful of rooms) there's no need for eventlet's concurrency model.
- **Word-pool exhaustion**: with only ~10 words at the "advanced" level, a
  long play session can exhaust the pool once the last-8-words exclusion
  list is considered. `Room.start_round` recovers by clearing recent-word
  history and retrying rather than crashing the game (see
  `test_start_round_recovers_when_word_pool_exhausted_by_history`).
- **Fuzzy match threshold**: Levenshtein distance ≤ 1 is only applied to
  answers ≥ 5 characters after normalization. Without the length floor,
  short words like "cat"/"car"/"cap" would all match each other at distance
  1, which defeats the purpose of guessing.
- **Port 5000 is unusable for local dev on macOS** — it collides with the
  macOS AirPlay Receiver service, which answers with a silent HTTP 403
  instead of a clear "address in use" error (very confusing to debug). The
  app defaults to port 5050 instead (`PORT` env var to override).
- **`flask_socketio.test_client.get_received()` drains the whole queue on
  every call**, not just events matching what you're looking for. A test
  helper that calls `get_received()` once per assertion will silently
  discard other already-queued events (e.g. asserting on `guess_result`
  consumes and loses a `round_started` event that arrived in the same
  batch). Fix: accumulate into a per-client running log
  (`tests/test_socket_integration.py::_drain`) instead of calling
  `get_received()` fresh each time.
- (Add more here as we hit them — Docker networking, Playwright flakiness,
  etc. Don't let this list go stale.)

---

## Origin / design history

The game began as a single-player prototype where a GPT model ("TabooGPT")
played the prompter role. That prototype (`apis/gpt.py`, now removed) made
live OpenAI API calls per turn, which made it slow, costly, and impossible
to unit test deterministically. The two-player rewrite replaces the AI
prompter with a second human player and a static, offline word bank —
same core gameplay loop, but real-time, free, testable, and (per direct
feedback) actually fun with a friend.

Original design notes and an example ChatGPT prompt used to prototype the
single-player mode are preserved below for historical reference.

### Example single-player session (superseded)

```
TabooGPT: 🔴它是紅色的 (Tā shì hóngsè de)
Player: A fire truck?
TabooGPT: 這不是救火車. 🚒 可以吃 🍔 (Zhè jiùhuǒ chē. Kěyǐ chī)
Player: 是西紅柿嗎?
TabooGPT: 不是。味道很甜 Bù shì. Wèidào hěn tián.
Player: What does weidao mean?
TabooGPT: It refers to the taste 👅
Player: 一個貧國！
TabooGPT: 沒錯Méicuò 🎉
上一輪你學到了... Shàng yīlún nǐ xué dàole…
* 味道 Wèidào – taste
讓我們再玩一次 Ràng wǒmen zài wán yīcì
它非常鋒利 Tā fēicháng fēnglì
```

### German prompt for beginners (superseded)

Here is a prompt used to chat directly with ChatGPT to play TabooGPT:

You are TabooGPT, a language-learning game assistant. The player is a
beginner learner (about kindergarten level) of the target language (e.g.,
German). Your job is to help them guess simple words by giving short, clear
clues in the target language, avoiding using the exact word or direct
giveaway emojis.

Rules & Style:
* Use simple sentences and basic vocabulary appropriate for a beginner.
* Provide clues with some repeated/reinforced phrases for learning (e.g., repeat words like Beine or sitzen in different rounds).
* Use emojis to support clues but never use an emoji that directly reveals the answer.
* When the player asks for help or doesn't understand, offer simple translations or explanations in English, but keep most communication in the target language.
* Encourage answers in target language, or gently correct near-misses in their native language.
* After each round, briefly review key new vocabulary from the clues.
