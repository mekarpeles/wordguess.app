from game.engine import Player
from game.rooms import RoomRegistry


def make_player(sid, name, native, target, level="beginner"):
    return Player(sid=sid, name=name, native_lang=native, target_lang=target, level=level)


def test_list_open_excludes_full_rooms():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", "en", "fr"))
    room.add_player(make_player("s2", "Bob", "fr", "en"))  # now full

    matches = registry.list_open(native_lang="fr", target_lang="en")
    assert matches == []


def test_list_open_excludes_empty_registry():
    registry = RoomRegistry()
    assert registry.list_open(native_lang="en", target_lang="fr") == []


def test_list_open_requires_strict_mutual_match():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", native="en", target="fr"))

    # Someone who is native French, learning English -- Alice's mirror.
    matches = registry.list_open(native_lang="fr", target_lang="en")
    assert len(matches) == 1
    assert matches[0]["code"] == room.code
    assert matches[0]["host_name"] == "Alice"


def test_list_open_rejects_one_directional_match():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", native="en", target="fr"))

    # This viewer's native matches Alice's target (fr), but the viewer's
    # target (es) doesn't match Alice's native (en) -- not a mutual match.
    matches = registry.list_open(native_lang="fr", target_lang="es")
    assert matches == []


def test_list_open_excludes_non_matching_language_pairs():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", native="en", target="fr"))

    matches = registry.list_open(native_lang="es", target_lang="zh")
    assert matches == []


def test_list_open_includes_level():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", native="en", target="fr", level="advanced"))

    matches = registry.list_open(native_lang="fr", target_lang="en")
    assert matches[0]["level"] == "advanced"


def test_list_open_returns_multiple_matching_rooms():
    registry = RoomRegistry()
    room1 = registry.create()
    room1.add_player(make_player("s1", "Alice", native="en", target="fr"))
    room2 = registry.create()
    room2.add_player(make_player("s2", "Carla", native="en", target="fr"))

    matches = registry.list_open(native_lang="fr", target_lang="en")
    codes = {m["code"] for m in matches}
    assert codes == {room1.code, room2.code}


def test_list_open_excludes_room_once_it_fills_up_via_registry_lookup():
    registry = RoomRegistry()
    room = registry.create()
    room.add_player(make_player("s1", "Alice", native="en", target="fr"))
    assert len(registry.list_open(native_lang="fr", target_lang="en")) == 1

    room.add_player(make_player("s2", "Bob", native="fr", target="en"))
    assert registry.list_open(native_lang="fr", target_lang="en") == []
