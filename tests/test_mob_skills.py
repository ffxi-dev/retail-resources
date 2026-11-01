"""scripts/mob_skills: entry i of ROM/27/80.DAT is mob skill 256 + i, the id LSB and the action packet use.

Run: `python -m unittest discover tests`
"""

import unittest

from models.strings import ParsedString, ParsedStringDat
from scripts.mob_skills.dump import rows


class MobSkillRows(unittest.TestCase):
    def test_ids_names_and_unused_entries(self):
        texts = ["#0", "Foot Kick", ".", "Fighting Stance \x03?", ""]
        parsed = ParsedStringDat(len(texts), [ParsedString(index=i, offset=0, text=t) for i, t in enumerate(texts)])
        self.assertEqual(rows(parsed), [{"id": 257, "name": "Foot Kick"}, {"id": 259, "name": "Fighting Stance"}])


if __name__ == "__main__":
    unittest.main()
