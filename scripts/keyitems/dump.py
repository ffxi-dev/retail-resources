import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from loguru import logger

from xi_tinkerer import parse_dmsg_table
from scripts.base import DumpScript
from writers.json import write_ndjson_gz
from writers.parquet import write_parquet

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _str(entry: dict) -> str:
    return entry.get("string", "") if isinstance(entry, dict) else ""


def _num(entry: dict) -> int:
    return entry.get("number", 0) if isinstance(entry, dict) else 0


def rows(lists: dict) -> list[dict]:
    """Key item rows from parse_dmsg_table's lists.

    A list's key is its position in the DAT, which is sorted for the key item menu.
    The key item id the server sends is the list's first number. Id 0 marks the
    placeholder entry and the menu's section headers ("-Temporary Key Items").
    """
    out = []
    for entries in lists.values():
        if not isinstance(entries, list) or len(entries) < 7:
            continue
        kid = _num(entries[0])
        name = _str(entries[4])
        if not kid or not name:
            continue
        out.append({
            "id": kid,
            "category": _num(entries[1]),
            "name": name,
            "name_plural": _str(entries[5]),
            "description": _str(entries[6]),
        })
    out.sort(key=lambda r: r["id"])
    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate key item ids")
    return out


class KeyItemDumper(DumpScript):
    """FFXI key item dumper: id, category number, name, plural, description."""
    produces = ["keyitems"]

    def __init__(self):
        with open(os.path.join(SCRIPT_DIR, "dats.yaml")) as f:
            self.spec = yaml.safe_load(f)

    def list_files(self) -> list[str]:
        return [self.spec["dat"]]

    def dump(self, version: str, base_path: str, output_dir: str):
        out = rows(parse_dmsg_table(os.path.join(base_path, self.spec["dat"]))["lists"])
        logger.info("Parsed {} key items", len(out))

        meta = {"version": version, "schema_version": 2}
        write_ndjson_gz(out, os.path.join(output_dir, "keyitems.ndjson.gz"), meta=meta)
        write_parquet(
            out, os.path.join(output_dir, "keyitems.parquet"),
            sort_by=["id"], row_group_size=1_000,
        )


if __name__ == "__main__":
    KeyItemDumper().run()
