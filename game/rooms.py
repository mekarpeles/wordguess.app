import random
import string

from game.engine import Room

CODE_ALPHABET = string.ascii_uppercase
CODE_LENGTH = 4


class RoomRegistry:
    def __init__(self):
        self._rooms: dict[str, Room] = {}

    def create(self) -> Room:
        code = self._new_code()
        room = Room(code=code)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get((code or "").strip().upper())

    def remove(self, code: str) -> None:
        self._rooms.pop(code, None)

    def list_open(self, native_lang: str, target_lang: str) -> list[dict]:
        """Rooms waiting for a second player, filtered to a strict mutual
        language match: the host's native language must be what the viewer
        wants to learn, AND the host must want to learn the viewer's native
        language. One-directional matches (host doesn't need the viewer's
        native language) are intentionally excluded -- see AGENTS.md."""
        matches = []
        for room in self._rooms.values():
            if len(room.players) != 1:
                continue
            host = next(iter(room.players.values()))
            if host.native_lang == target_lang and host.target_lang == native_lang:
                matches.append({"code": room.code, "host_name": host.name, "level": host.level})
        return matches

    def _new_code(self) -> str:
        while True:
            code = "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))
            if code not in self._rooms:
                return code
