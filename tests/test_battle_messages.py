"""scripts/battle_messages: the client's battle messages with their control codes as tokens.

Run: `python -m unittest discover tests`
"""

import unittest

from models.strings import ParsedString, ParsedStringDat
from scripts.battle_messages.dump import rows, tokens

END = "\x7f1\x00\x07"


class Tokens(unittest.TestCase):
    def test_melee_hit(self):  # message 1, as ROM/27/72.DAT holds it
        raw = "\x7f\x08\x00[The /]\x01\x01\x10 \x7f\x07\x00[hits/hit] \x7f\x08\x01[the /]\x01\x01\x11 for \x12\x01 point\x7f\x06\x01[/s] of damage." + END
        self.assertEqual(
            tokens(raw), "{the actor|The |}{actor} {verb actor|hits|hit} {the target|the |}{target} for {number 1} point{plural 1||s} of damage."
        )

    def test_spell_resist_has_two_lines(self):  # message 85
        raw = "\x7f\x08\x00[The /]\x01\x01\x10 \x7f\x07\x00[casts/cast] \x10\x00.\x07\x7f\x04\x00\x7f\x08\x01[The /]\x01\x01\x11 \x7f\x07\x01[resists/resist] the spell." + END
        self.assertEqual(
            tokens(raw), "{the actor|The |}{actor} {verb actor|casts|cast} {spell 0}.\n{the target|The |}{target} {verb target|resists|resist} the spell."
        )

    def test_tp_move_and_job_ability(self):  # messages 43 and 100
        self.assertEqual(tokens("\x01\x01\x10 readies \x16\x01." + END), "{actor} readies {weapon_skill 1}.")
        self.assertEqual(tokens("\x01\x01\x10 uses \x7f\x0f\x00." + END), "{actor} uses {ability 0}.")

    def test_tables_gender_and_gil(self):
        self.assertEqual(tokens("Additional effect: \x01\x05\x13\x02\x02\x00\x00." + END), "Additional effect: {status 2}.")
        self.assertEqual(tokens("\x01\x01\x11 is \x01\x05\x14\x02\x01\x00\x00!" + END), "{target} is {status_passive 1}!")
        self.assertEqual(tokens("You obtain \x01\x01\x01 \x01\x05'\x02\x00\x00\x00." + END), "You obtain {item_a 0}.")
        self.assertEqual(tokens("with \x7f\x11[his/her] shield." + END), "with {gender target|his|her} shield.")
        self.assertEqual(tokens("\x01\x01\x11 obtains \x7f4\x00." + END), "{target} obtains {gil 0}.")
        self.assertEqual(tokens("You have undertaken \x072\x01\x05A\x02\x00\x00\x00.\x073" + END), "You have undertaken {table_65 0}.")

    def test_unknown_codes_are_left_out(self):
        texts = ["dummy" + END, "\x01\x01\x10\x02L\x106\x0eY" + END, "", "Job changed." + END]
        parsed = ParsedStringDat(len(texts), [ParsedString(index=i, offset=0, text=t) for i, t in enumerate(texts)])
        self.assertEqual(rows(parsed), [{"id": 0, "text": "dummy"}, {"id": 3, "text": "Job changed."}])


if __name__ == "__main__":
    unittest.main()
