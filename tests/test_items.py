"""parsers/items: a client before Sep 2026 has 0xC00 records with fields at 0x0E; later ones 0x1400, at 0x10.

Run: `python -m unittest discover tests`
"""

import os
import struct
import tempfile
import unittest

from parsers.items import parse_all_items


def encrypt(data: bytes) -> bytes:
    return bytes(((b << 5) | (b >> 3)) & 0xFF for b in data)


def usable(item_id: int, name: str, cast_time_raw: int, new: bool) -> bytes:
    rec = bytearray(0x1400 if new else 0xC00)
    header = struct.pack("<HHH", item_id, 0, 0) + (b"\0\0" if new else b"") + struct.pack("<HHHH", 12, 7, 2002, 0)
    rec[: len(header)] = header
    struct.pack_into("<H", rec, len(header), cast_time_raw)
    struct.pack_into("<III", rec, 0x30, 5, 0x2C, 0)  # the English string table: 5 entries, the name's at 0x2C
    for i in range(1, 5):
        struct.pack_into("<II", rec, 0x34 + i * 8, 0, 1)
    rec[0x78 : 0x78 + len(name)] = name.encode()
    return encrypt(bytes(rec))


class ItemLayouts(unittest.TestCase):
    def parse(self, new: bool):
        with tempfile.TemporaryDirectory() as d:
            records = usable(5414, "Glowing Lamp", 0, new) + usable(5415, "Hero's Reflections", 8, new)
            for name in ("en.DAT", "ja.DAT"):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(records)
            spec = {"item_dats": [{"en": "en.DAT", "ja": "ja.DAT", "base_id": 5414, "max_count": 2}]}
            return [(i.id, i.name.english, i.resource_id, i.type, i.usable.cast_time) for i in parse_all_items(d, spec)]

    def test_both_layouts(self):
        want = [(5414, "Glowing Lamp", 2002, "Usable", None), (5415, "Hero's Reflections", 2002, "Usable", 2.0)]
        self.assertEqual(self.parse(new=False), want)
        self.assertEqual(self.parse(new=True), want)


if __name__ == "__main__":
    unittest.main()
