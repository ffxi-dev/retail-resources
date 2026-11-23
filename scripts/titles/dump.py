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

UNUSED = {"", "0"}  # unused slots hold "0" or nothing, in both languages


def _name(lists: dict, tid: int) -> str:
    entries = lists.get(str(tid))
    return entries[0].get("string", "") if entries and isinstance(entries[0], dict) else ""


def rows(en: dict, ja: dict) -> list[dict]:
    """Title rows from the English and Japanese parse_dmsg_table lists.

    Entry i is title i, the id the server sends and LSB's xi.title uses. Id 0 is "N/A", shown with no title.
    """
    out = []
    for tid in sorted(int(k) for k in en):
        name = _name(en, tid)
        if name not in UNUSED:
            out.append({"id": tid, "name": name, "name_ja": _name(ja, tid)})
    return out


class TitleDumper(DumpScript):
    """FFXI title dumper: id, English name, Japanese name."""

    produces = ["titles"]

    def __init__(self):
        with open(os.path.join(SCRIPT_DIR, "dats.yaml")) as f:
            self.spec = yaml.safe_load(f)

    def list_files(self) -> list[str]:
        return [self.spec["en"], self.spec["ja"]]

    def dump(self, version: str, base_path: str, output_dir: str):
        en = parse_dmsg_table(os.path.join(base_path, self.spec["en"]))["lists"]
        ja = parse_dmsg_table(os.path.join(base_path, self.spec["ja"]))["lists"]
        out = rows(en, ja)
        logger.info("Parsed {} titles", len(out))

        meta = {"version": version, "schema_version": 1}
        write_ndjson_gz(out, os.path.join(output_dir, "titles.ndjson.gz"), meta=meta)
        write_parquet(out, os.path.join(output_dir, "titles.parquet"), sort_by=["id"], row_group_size=1_000)


if __name__ == "__main__":
    TitleDumper().run()
