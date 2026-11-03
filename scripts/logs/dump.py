import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from loguru import logger

from xi_tinkerer import parse_dmsg_table
from scripts.base import DumpScript
from writers.json import write_ndjson_gz
from writers.parquet import write_parquet

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Unused slots keep a Japanese placeholder name ("SDクエスト32") or an empty client line ("Client:\n　").
PLACEHOLDER_NAME = re.compile(r"[\u3000-\u30ff\u4e00-\u9fff\uff00-\uffef]")
PLACEHOLDER_TEXT = re.compile(r"(Client[:：]|依頼者)\s*")


def _str(entry) -> str:
    return entry.get("string", "") if isinstance(entry, dict) else ""


def log_name(title: str) -> str:
    """"Outlands: Current Quests" -> "Outlands"; a mission log's title is its name."""
    return title.split(":")[0]


def entries(lists: dict) -> list[tuple[int, str, str]]:
    """(id, name, description) per entry, in the DAT's order."""
    out = []
    for k in sorted(lists, key=int):
        e = lists[k]
        if isinstance(e, list) and len(e) >= 3 and isinstance(e[0], dict) and "number" in e[0]:
            out.append((e[0]["number"], _str(e[1]), _str(e[2])))
    return out


def rows(kind: str, log_id: int, log: str, items: list[tuple[int, str, str]]) -> list[dict]:
    """One row per id. A quest's id is its bit in the 0x056 log; a mission's is the value 0x056 sends.
    Mission logs nest steps under chapters with "__" per level; a chapter shares its first step's id,
    and the step wins. A quest name's leading "+" marks the quests the client lists as repeatable."""
    best: dict[int, dict] = {}
    for id_, name, text in items:
        if not name or PLACEHOLDER_NAME.search(name) or PLACEHOLDER_TEXT.fullmatch(text):
            continue
        row = {"log_id": log_id, "log": log, "id": id_}
        if kind == "quests":
            row |= {"name": name.removeprefix("+"), "repeatable": name.startswith("+")}
        else:
            stripped = name.lstrip("_")
            if not stripped:
                continue
            row |= {"name": stripped, "depth": (len(name) - len(stripped)) // 2}
        row["description"] = text
        if id_ not in best or kind == "missions" and row["depth"] > best[id_]["depth"]:
            best[id_] = row
    return sorted(best.values(), key=lambda r: r["id"])


class LogDumper(DumpScript):
    """FFXI quest and mission names by log and id, as the 0x056 log packet numbers them."""
    produces = ["quests", "missions"]

    def __init__(self):
        with open(os.path.join(SCRIPT_DIR, "dats.yaml")) as f:
            self.spec = yaml.safe_load(f)

    def list_files(self) -> list[str]:
        return [self.spec["menu"]] + [log["dat"] for kind in ("quests", "missions") for log in self.spec[kind]]

    def dump(self, version: str, base_path: str, output_dir: str):
        titles = parse_dmsg_table(os.path.join(base_path, self.spec["menu"]))["lists"]
        meta = {"version": version, "schema_version": 1}
        for kind in ("quests", "missions"):
            out = []
            for log in self.spec[kind]:
                name = log_name(_str(titles[str(log["title"])][0]))
                lists = parse_dmsg_table(os.path.join(base_path, log["dat"]))["lists"]
                out += rows(kind, log["log_id"], name, entries(lists))
            logger.info("Parsed {} {}", len(out), kind)
            write_ndjson_gz(out, os.path.join(output_dir, f"{kind}.ndjson.gz"), meta=meta)
            write_parquet(out, os.path.join(output_dir, f"{kind}.parquet"), sort_by=["log_id", "id"])


if __name__ == "__main__":
    LogDumper().run()
