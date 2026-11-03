"""scripts/r2_upload: rebuild-index publishes versions.json only when every manifest reads and parses.

Run: `python -m unittest discover tests`
"""

import io
import json
import os
import unittest
from unittest import mock

from botocore.exceptions import ClientError

from scripts import r2_upload


class FakeS3:
    def __init__(self, bodies):
        self.bodies = bodies  # key -> bytes, or an exception to raise on GET
        self.puts = []

    def get_paginator(self, _name):
        keys = list(self.bodies)
        return mock.Mock(paginate=lambda **_: [{"Contents": [{"Key": k} for k in keys]}])

    def get_object(self, Bucket, Key):
        body = self.bodies[Key]
        if isinstance(body, Exception):
            raise body
        return {"Body": io.BytesIO(body)}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def manifest(version):
    return json.dumps({"version": version, "generated_at": "2026-01-01T00:00:00+00:00", "files": {"a.json": {}}}).encode()


GOOD = {"versions/30251105_0/manifest.json": manifest("30251105_0")}


def rebuild(s3):
    with mock.patch.dict(os.environ, {"BUCKET": "test"}), mock.patch.object(r2_upload, "_client", return_value=s3):
        r2_upload.rebuild_index()


class RebuildIndex(unittest.TestCase):
    def test_publishes_when_every_manifest_reads(self):
        s3 = FakeS3(dict(GOOD))
        rebuild(s3)
        self.assertEqual(len(s3.puts), 1)
        self.assertEqual(json.loads(s3.puts[0]["Body"])["latest"], "30251105_0")

    def test_failed_get_leaves_index_alone(self):
        err = ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "GetObject")
        s3 = FakeS3({**GOOD, "versions/30251201_0/manifest.json": err})
        with self.assertRaises(SystemExit):
            rebuild(s3)
        self.assertEqual(s3.puts, [])

    def test_malformed_manifest_leaves_index_alone(self):
        for body in (b"{not json", b"{}", b"[]"):
            s3 = FakeS3({**GOOD, "versions/30251201_0/manifest.json": body})
            with self.subTest(body=body), self.assertRaises(SystemExit):
                rebuild(s3)
            self.assertEqual(s3.puts, [])


if __name__ == "__main__":
    unittest.main()
