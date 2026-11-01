"""Lookup tables the client keeps in FFXiMain.dll's .data: which DAT file holds a player's models and motions.

Each table is found by its first entries, the way xim and the in-browser replay find them. The anchors have held
from the November 2022 build to October 2026; if one stops matching, the dump fails rather than guess.
"""

import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from loguru import logger

from scripts.base import DumpScript
from writers.json import write_json

DLL = "FFXiMain.dll"
SCHEMA_VERSION = 1

# Race ids as the look (GrapIDTbl) carries them. 0 copies hume male; 29-36 are the children and chocobos.
PLAYER_RACES = 9  # 0-8
ALL_RACES = 37  # 0-36
# Race id to its block in the equipment table, as the client's pointer table maps them (0x1035f378 in the Oct 2026 build).
EQUIPMENT_BLOCK = {0: 0, **{r: r - 1 for r in range(1, 9)}, **{r: r - 21 for r in range(29, 37)}}

# Motion tables: a u16 (or u32) per player race, then, 4-byte aligned, a pair per race for skirt kinds 1 and 2.
# name: (anchor, width, description)
MOTIONS = {
    "battle": (
        9672,
        2,
        "Engaged motions, one hand armed. File = value[race] + the main weapon's motion type (byte 3 of its info block).",
    ),
    "dual_main": (40815, 2, "Engaged motions for the main hand when dual wielding. File = value[race] + main weapon motion type."),
    "dual_off": (40431, 2, "Engaged motions for the off hand when dual wielding. File = value[race] + off-hand weapon motion type."),
    "emote": (10056, 2, "Emotes. File = value[race] + emote id."),
    "weaponskill": (33227, 2, "Weapon skill motions, action category 3, animation ids below 256. File = value[race] + animation id."),
    "weaponskill_high": (
        61451,
        2,
        "Weapon skill motions, action category 3, animation ids 256 and up. File = value[race] + animation id - 256.",
    ),
    "dance": (58041, 2, "Dancer motions, action category 14. File = value[race] + animation id."),
    "rune_fencer": (88035, 4, "Rune Fencer motions, action category 15. File = value[race] + animation id."),
    "action": (38603, 2, "Other action motions. File = value[race] + n: 1 fishing, 4 sitting on a chair, 5 riding a mount."),
}
SKIRT = "Skirt layer for {name}: value[race][k - 1] + the same offset, where k is the skirt kind (byte 9 of the body's info block)."


def _find(dll: bytes, pattern: bytes, align: int = 2) -> int:
    """Offset of the only aligned match of pattern; raises if there is none or more than one."""
    hits, at = [], dll.find(pattern)
    while at >= 0:
        if at % align == 0:
            hits.append(at)
        at = dll.find(pattern, at + 1)
    if len(hits) != 1:
        raise ValueError(f"{pattern.hex()} matched {len(hits)} times in {DLL}")
    return hits[0]


def _race_table(dll: bytes, anchor: int, width: int) -> tuple[list[int], list[list[int]]]:
    fmt = "<H" if width == 2 else "<I"
    at = _find(dll, struct.pack(f"<2{fmt[1]}", anchor, anchor), width)
    values = [struct.unpack_from(fmt, dll, at + i * width)[0] for i in range(PLAYER_RACES)]
    skirt_at = (at + PLAYER_RACES * width + 3) & ~3
    skirt = [list(struct.unpack_from(f"<2{fmt[1]}", dll, skirt_at + i * 2 * width)) for i in range(PLAYER_RACES)]
    # The skirt files follow the plain ones; if they do not, the layout moved.
    if not all(values[r] and values[r] < skirt[r][0] < skirt[r][1] for r in range(1, PLAYER_RACES)) or skirt[0] != skirt[1]:
        raise ValueError(f"table at {at:#x} (anchor {anchor}) does not have the expected layout")
    return values, skirt


def read(dll: bytes) -> dict:
    out = {}

    at = _find(dll, struct.pack("<3H", 7072, 7072, 10248))
    out["race_files"] = {
        "description": (
            "First file of a race's model set, by race id 0-36. +0 skeleton and lower-body motions, +1 upper-body motions, "
            "+3 and +4 the skirt layer for skirt kinds 1 and 2."
        ),
        "values": [struct.unpack_from("<H", dll, at + r * 2)[0] for r in range(ALL_RACES)],
    }

    at = _find(dll, struct.pack("<2I", 7080, 32), 4)
    blocks = [[[list(struct.unpack_from("<2I", dll, at + b * 0x1B0 + slot * 0x30 + i * 8)) for i in range(6)] for slot in range(9)] for b in range(16)]
    out["equipment"] = {
        "description": (
            "Equipment model to file, by race id then slot (0 face, 1 head, 2 body, 3 hands, 4 legs, 5 feet, 6 main, 7 sub, "
            "8 ranged). Each slot is a list of [first file, count] runs; model ids count on through the runs. Null for races "
            "with no table."
        ),
        "values": [[[run for run in slot if run[0]] for slot in blocks[EQUIPMENT_BLOCK[r]]] if r in EQUIPMENT_BLOCK else None for r in range(ALL_RACES)],
    }

    for name, (anchor, width, description) in MOTIONS.items():
        values, skirt = _race_table(dll, anchor, width)
        out[name] = {"description": description, "values": values}
        out[f"{name}_skirt"] = {"description": SKIRT.format(name=name), "values": skirt}

    at = _find(dll, struct.pack("<2H", 39307, 39307))
    out["fishing_rod"] = {
        "description": "Fishing rod models. File = value[race] + the ranged slot's model id.",
        "values": [struct.unpack_from("<H", dll, at + r * 2)[0] for r in range(PLAYER_RACES)],
    }
    return out


class ClientTablesDumper(DumpScript):
    """Lookup tables from FFXiMain.dll: race, equipment and motion file ids."""

    produces = ["client_tables"]

    def list_files(self) -> list[str]:
        return [DLL]

    def dump(self, version: str, base_path: str, output_dir: str):
        with open(os.path.join(base_path, DLL), "rb") as f:
            tables = read(f.read())
        logger.info("Read {} tables from {}", len(tables), DLL)

        write_json(tables, os.path.join(output_dir, "client_tables.json"))
        with open(os.path.join(output_dir, "client_tables.meta.json"), "w", encoding="utf-8") as f:
            json.dump({"version": version, "schema_version": SCHEMA_VERSION, "count": len(tables)}, f, indent=2)


if __name__ == "__main__":
    ClientTablesDumper().run()
