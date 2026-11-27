"""writers: the same records give the same bytes, so a rerun names the same revision.

Run: `python -m unittest discover tests`
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from writers.json import write_ndjson_gz


class Gzip(unittest.TestCase):
    def test_same_records_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "a.ndjson.gz"), Path(d, "b", "a.ndjson.gz")
            b.parent.mkdir()
            write_ndjson_gz([{"id": 1}], str(a))
            with mock.patch.object(time, "time", return_value=time.time() + 3600):
                write_ndjson_gz([{"id": 1}], str(b))
            self.assertEqual(a.read_bytes(), b.read_bytes())


if __name__ == "__main__":
    unittest.main()
