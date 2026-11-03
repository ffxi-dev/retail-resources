"""scripts/logs: quest and mission names by log and id, as the 0x056 log packet numbers them.

Run: `python -m unittest discover tests`
"""

import unittest

from scripts.logs.dump import entries, log_name, rows


def dat(*items):
    """parse_dmsg_table's lists for (id, name, description) entries."""
    return {str(i): [{"number": n}, {"string": s}, {"string": d}] for i, (n, s, d) in enumerate(items)}


class Quests(unittest.TestCase):
    def test_names_repeatable_and_placeholders(self):
        lists = dat(
            (0, "A Sentry's Peril", "Client: Glenne"),
            (32, "SDクエスト32", "依頼者\n　"),
            (99, "Windurst Quest #99", "Client:\n　"),
            (110, "+Spice Gals", "Client: Rouva"),
        )
        self.assertEqual(rows("quests", 0, "San d'Oria", entries(lists)), [
            {"log_id": 0, "log": "San d'Oria", "id": 0, "name": "A Sentry's Peril", "repeatable": False,
             "description": "Client: Glenne"},
            {"log_id": 0, "log": "San d'Oria", "id": 110, "name": "Spice Gals", "repeatable": True,
             "description": "Client: Rouva"},
        ])

    def test_log_name_from_menu_title(self):
        self.assertEqual(log_name("Outlands: Current Quests"), "Outlands")
        self.assertEqual(log_name("Coalition: Current Assignments"), "Coalition")
        self.assertEqual(log_name("Chains of Promathia"), "Chains of Promathia")


class Missions(unittest.TestCase):
    def test_a_step_wins_over_the_chapter_sharing_its_id(self):
        lists = dat(
            (0, "Rhapsodies of Vana'diel", "　Even the slightest ripple"),
            (110, "Chapter One: Creation and Rebirth", ""),
            (110, "__Resonance", "Mission Orders: A vision"),
            (330, "____Emerald Waters", "Mission Orders: Find"),
            (999, "__", ""),
        )
        got = [(r["id"], r["name"], r["depth"]) for r in rows("missions", 13, "Rhapsodies of Vana'diel", entries(lists))]
        self.assertEqual(got, [(0, "Rhapsodies of Vana'diel", 0), (110, "Resonance", 1), (330, "Emerald Waters", 2)])


if __name__ == "__main__":
    unittest.main()
