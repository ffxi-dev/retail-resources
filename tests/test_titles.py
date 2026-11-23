"""scripts/titles: entry i of ROM/180/78.DAT (English) and ROM/180/77.DAT (Japanese) is title i.

Run: `python -m unittest discover tests`
"""

import unittest

from scripts.titles.dump import rows


def table(names: list[str]) -> dict:
    return {str(i): [{"string": n}] for i, n in enumerate(names)}


class TitleRows(unittest.TestCase):
    def test_ids_names_and_unused_entries(self):
        en = table(["N/A", "Fodderchief Flayer", "0", "", "Giant Killer"])
        ja = table(["なし", "フォッダーチーフ　フレーヤー", "0", "", "ジャイアントキラー"])
        self.assertEqual(
            rows(en, ja),
            [
                {"id": 0, "name": "N/A", "name_ja": "なし"},
                {"id": 1, "name": "Fodderchief Flayer", "name_ja": "フォッダーチーフ　フレーヤー"},
                {"id": 4, "name": "Giant Killer", "name_ja": "ジャイアントキラー"},
            ],
        )

    def test_missing_japanese_entry(self):
        self.assertEqual(rows(table(["N/A", "Hellsbane"]), table(["なし"]))[1], {"id": 1, "name": "Hellsbane", "name_ja": ""})


if __name__ == "__main__":
    unittest.main()
