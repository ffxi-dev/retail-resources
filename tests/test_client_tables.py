"""scripts/client_tables: the dump matches what the in-browser replay reads from FFXiMain.dll at run time.

The replay (xi-visualizer-replay, src/graphics/xi_actor.ts readDllTables and xi_effect.ts readDll) finds each table by
its first u16s and reads 40 u16s from there. `replay_tables` below does the same, so the test fails if the dump and
the replay ever disagree. Needs a local install; skipped without one.

Run: `python -m unittest discover tests`
"""

import os
import struct
import unittest

from scripts.base import DEFAULT_BASE
from scripts.client_tables.dump import DLL, read

PATH = os.path.join(os.environ.get("FFXI_BASE", DEFAULT_BASE), DLL)


def replay_tables(dll: bytes) -> dict:
    """The replay's readers, line for line."""

    def find(*words):
        pattern = struct.pack(f"<{len(words)}H", *words)
        at = dll.find(pattern)
        while at % 2:
            at = dll.find(pattern, at + 1)
        return at

    def u16s(at, stride=2, offset=0):
        return [struct.unpack_from("<H", dll, at + i * stride + offset)[0] for i in range(40)]

    equip = find(7080, 0, 32, 0)
    slots = [
        [[r for r in (list(struct.unpack_from("<2I", dll, equip + race * 0x1B0 + slot * 0x30 + i * 8)) for i in range(6)) if r[0]] for slot in range(9)]
        for race in range(16)
    ]
    return {
        "slots": slots,
        "skeletons": u16s(find(7072, 7072)),
        "battle": u16s(find(9672, 9672)),
        "battleDual": u16s(find(40815, 40815)),
        "dualOff": u16s(find(0x9DEF, 0x9DEF)),
        "skirt": u16s(find(9800, 9928, 9800, 9928), 4, 2),
        "skirtDual": u16s(find(40943, 41071, 40943, 41071), 4, 2),
        "weaponskill": u16s(find(33227, 33227)),
        "dance": u16s(find(58041, 58041)),
        "action": u16s(find(38603, 38603)),
    }


@unittest.skipUnless(os.path.isfile(PATH), f"no {DLL} at {PATH}")
class ClientTablesMatchReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PATH, "rb") as f:
            dll = f.read()
        cls.ours = {k: v["values"] for k, v in read(dll).items()}
        cls.replay = replay_tables(dll)

    def test_race_tables(self):
        ours, replay = self.ours, self.replay
        self.assertEqual(ours["race_files"], replay["skeletons"][:37])
        for theirs, mine in [
            ("battle", "battle"),
            ("battleDual", "dual_main"),
            ("dualOff", "dual_off"),
            ("weaponskill", "weaponskill"),
            ("dance", "dance"),
            ("action", "action"),
        ]:
            self.assertEqual(ours[mine], replay[theirs][:9], mine)
        # The replay always takes skirt kind 2.
        self.assertEqual([p[1] for p in ours["battle_skirt"]], replay["skirt"][:9])
        self.assertEqual([p[1] for p in ours["dual_main_skirt"]], replay["skirtDual"][:9])

    def test_equipment(self):
        # The replay's tableIndex: races 1-8 use blocks 1-8, 29-36 use 9-16.
        for race in [*range(1, 9), *range(29, 37)]:
            block = race if race <= 8 else race - 20
            self.assertEqual(self.ours["equipment"][race], self.replay["slots"][block - 1], race)

    def test_known_values(self):
        self.assertEqual(self.ours["race_files"][1], 7072)  # hume male
        self.assertEqual(self.ours["equipment"][1][0], [[7080, 32]])  # hume male faces
        self.assertEqual(self.ours["battle_skirt"][1], [9800, 9928])


if __name__ == "__main__":
    unittest.main()
