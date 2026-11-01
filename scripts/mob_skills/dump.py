import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from loguru import logger

from models.strings import ParsedStringDat
from parsers.strings import parse_string_dat_english
from scripts.base import DumpScript
from writers.json import write_ndjson_gz
from writers.parquet import write_parquet

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Entry i names the mob skill the action packet (0x028, category 11) sends as 256 + i, as LSB numbers them.
FIRST_ID = 256
UNUSED = re.compile(r"^(\.|#\d+)?$")  # "." and "#123" mark unused entries


def rows(parsed: ParsedStringDat) -> list[dict]:
    out = []
    for s in parsed.strings:
        name = re.sub(r"[\x00-\x1f].?", "", s.text).strip()  # drop control codes and their argument byte
        if not UNUSED.match(name):
            out.append({"id": FIRST_ID + s.index, "name": name})
    return sorted(out, key=lambda r: r["id"])


class MobSkillDumper(DumpScript):
    """FFXI mob skill names, by the id the action packet sends."""
    produces = ["mob_skills"]

    def __init__(self):
        with open(os.path.join(SCRIPT_DIR, "dats.yaml")) as f:
            self.spec = yaml.safe_load(f)

    def list_files(self) -> list[str]:
        return [self.spec["dat"]]

    def dump(self, version: str, base_path: str, output_dir: str):
        out = rows(parse_string_dat_english(os.path.join(base_path, self.spec["dat"])))
        logger.info("Parsed {} mob skills", len(out))

        meta = {"version": version, "schema_version": 1}
        write_ndjson_gz(out, os.path.join(output_dir, "mob_skills.ndjson.gz"), meta=meta)
        write_parquet(out, os.path.join(output_dir, "mob_skills.parquet"), sort_by=["id"], row_group_size=1_000)


if __name__ == "__main__":
    MobSkillDumper().run()
