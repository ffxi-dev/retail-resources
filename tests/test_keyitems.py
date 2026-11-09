"""scripts/keyitems: the key item id is each entry's first number, not its position in ROM/175/35.DAT.

Run: `python -m unittest discover tests`
"""

import unittest

from scripts.keyitems.dump import rows


def entry(kid: int, name: str) -> list[dict]:
    return [{"number": kid}, {"number": 2}, {"string": ""}, {"string": ""}, {"string": name}, {"string": name + "s"}, {"string": ""}]


class KeyItemRows(unittest.TestCase):
    def test_ids_from_first_number(self):
        # Positions and ids from 30261006_0.
        lists = {
            "0": entry(0, "in-text name"),
            "354": entry(1248, "whisper of radiance"),
            "1248": entry(2211, "Mor. FS building mat. container"),
            "1632": entry(0, "-Temporary Key Items"),
            "1636": entry(8, "airship pass"),
        }
        self.assertEqual(
            [(r["id"], r["name"]) for r in rows(lists)],
            [(8, "airship pass"), (1248, "whisper of radiance"), (2211, "Mor. FS building mat. container")],
        )

    def test_duplicate_ids_fail(self):
        with self.assertRaises(ValueError):
            rows({"1": entry(5, "a"), "2": entry(5, "b")})


if __name__ == "__main__":
    unittest.main()
