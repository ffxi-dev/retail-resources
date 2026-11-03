"""The client's battle messages, by the message id 0x028 results and 0x029 send, with its placeholders as tokens.

Token grammar and slots: docs/FORMATS.md, battle_messages.
"""

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

WHO = {"\x00": "actor", "\x01": "target", "\x10": "actor", "\x11": "target"}
CHOICE = {"\x06": "plural", "\x07": "verb", "\x08": "the"}
VALUE = {"\x05": "skill", "\x10": "spell", "\x12": "number", "\x14": "time", "\x16": "weapon_skill"}
VALUE_7F = {"\x0f": "ability", "\x1b": "tenths", "4": "gil"}
TABLE = {0x13: "status", 0x14: "status_passive", 0x26: "item", 0x27: "item_a", 0x28: "item_plural", 0x42: "keyitem"}

CODE = re.compile(
    r"\x7f(?P<choice>[\x06\x07\x08])(?P<n>.)\[(?P<a>[^/\]]*)/(?P<b>[^\]]*)\]"
    r"|\x7f(?P<gender>[\x10\x11])\[(?P<he>[^/\]]*)/(?P<she>[^\]]*)\]"
    r"|\x7f[\x041].|\x01[^\x01\x05]|\x1f.|\x07[23](?!nd|rd)"  # line marks, prompts, colors, brackets: nothing shown
    r"|\x01\x01(?P<name>[\x10\x11])"
    r"|(?:\x01\x01\x01 )?\x01\x05(?P<table>.)\x02(?P<tn>[\x00-\x07])\x00\x00"
    r"|\x7f(?P<sub>.)(?P<sn>[\x00-\x07])"
    r"|(?P<value>[\x05\x10\x12\x14\x16])(?P<vn>[\x00-\x07])"
    r"|\x07",
    re.S,
)


def _token(m: re.Match) -> str:
    g = m.groupdict()
    if g["choice"]:
        kind = CHOICE[g["choice"]]
        arg = str(ord(g["n"])) if kind == "plural" else WHO.get(g["n"], str(ord(g["n"])))
        return f"{{{kind} {arg}|{g['a']}|{g['b']}}}"
    if g["gender"]:
        return f"{{gender {WHO[g['gender']]}|{g['he']}|{g['she']}}}"
    if g["name"]:
        return f"{{{WHO[g['name']]}}}"
    if g["table"]:
        t = ord(g["table"])
        return f"{{{TABLE[t]} {ord(g['tn'])}}}" if t in TABLE else f"{{table_{t} {ord(g['tn'])}}}"
    if g["sub"]:
        return f"{{{VALUE_7F.get(g['sub'], 'value')} {ord(g['sn'])}}}"
    if g["value"]:
        return f"{{{VALUE[g['value']]} {ord(g['vn'])}}}"
    return "\n" if m.group(0) == "\x07" else ""


def tokens(text: str) -> str | None:
    """The message with its control codes as tokens; None when codes are left that the grammar does not know."""
    out = CODE.sub(_token, text).strip()
    return None if re.search(r"[\x00-\x09\x0b-\x1f\x7f]", out) else out


def rows(parsed: ParsedStringDat) -> list[dict]:
    out = []
    for s in parsed.strings:
        text = tokens(s.text)
        if text:
            out.append({"id": s.index, "text": text})
        else:
            logger.debug("Left out message {}: {!r}", s.index, s.text)
    return out


class BattleMessageDumper(DumpScript):
    """FFXI battle messages, by the id 0x028 and 0x029 send."""

    produces = ["battle_messages"]

    def __init__(self):
        with open(os.path.join(SCRIPT_DIR, "dats.yaml")) as f:
            self.spec = yaml.safe_load(f)

    def list_files(self) -> list[str]:
        return [self.spec["dat"]]

    def dump(self, version: str, base_path: str, output_dir: str):
        out = rows(parse_string_dat_english(os.path.join(base_path, self.spec["dat"])))
        logger.info("Parsed {} battle messages", len(out))

        meta = {"version": version, "schema_version": 1}
        write_ndjson_gz(out, os.path.join(output_dir, "battle_messages.ndjson.gz"), meta=meta)
        write_parquet(out, os.path.join(output_dir, "battle_messages.parquet"), sort_by=["id"], row_group_size=1_000)


if __name__ == "__main__":
    BattleMessageDumper().run()
