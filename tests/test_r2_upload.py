"""scripts/r2_upload: publish writes an immutable revision and resumes when stopped; rebuild-index
publishes versions.json only when every manifest reads and parses; drop-copies deletes the old layout's
copies only of a version whose revision holds every file.

Run: `python -m unittest discover tests`
"""

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
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


class Store:
    """An in-memory bucket. `fail_after` puts succeed, then the next one raises, as a stopped run."""

    def __init__(self):
        self.objects = {}  # key -> (bytes, metadata)
        self.uploads = []
        self.fail_after = None

    def _put(self, key, body, meta):
        if self.fail_after is not None:
            if self.fail_after == 0:
                raise RuntimeError("stopped")
            self.fail_after -= 1
        self.objects[key] = (body, meta or {})

    def upload_file(self, path, Bucket, Key, ExtraArgs):
        self.uploads.append(Key)
        self._put(Key, Path(path).read_bytes(), ExtraArgs.get("Metadata"))

    def put_object(self, Bucket, Key, Body, Metadata=None, **_):
        self._put(Key, Body, Metadata)

    def get_paginator(self, _name):
        return mock.Mock(paginate=lambda Prefix, **_: [{"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)]}])

    def delete_object(self, Bucket, Key):
        del self.objects[Key]

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {"Metadata": self.objects[Key][1]}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def body(self, key):
        return json.loads(self.objects[key][0])


def dump(files):
    d = Path(tempfile.mkdtemp())
    for name, data in files.items():
        (d / name).write_bytes(data)
    return d


def publish(store, version, dist):
    with mock.patch.dict(os.environ, {"BUCKET": "test"}), mock.patch.object(r2_upload, "_client", return_value=store):
        return r2_upload.publish(version, dist)


V = "30261102_1"
OLD = {"items.parquet": b"old items", "items.meta.json": b"{}"}
NEW = {"items.parquet": b"new items", "items.meta.json": b"{}"}


class Publish(unittest.TestCase):
    def test_writes_a_revision_and_points_the_version_at_it(self):
        s = Store()
        rev = publish(s, V, dump(OLD))
        pointer = s.body(f"versions/{V}/manifest.json")
        self.assertEqual(pointer["revision"], rev)
        self.assertEqual(pointer["base"], f"revisions/{V}/{rev}/")
        self.assertEqual(s.objects[f"revisions/{V}/{rev}/items.parquet"][0], b"old items")
        self.assertNotIn(f"versions/{V}/items.parquet", s.objects, "no copy in the old layout")
        self.assertEqual(s.body(f"revisions/{V}/{rev}/manifest.json"), pointer)
        self.assertIn("xi-events", pointer["source"]["packages"])

    def test_same_bytes_upload_nothing_and_keep_the_manifest(self):
        s = Store()
        rev = publish(s, V, dump(OLD))
        first = s.body(f"versions/{V}/manifest.json")
        s.uploads.clear()
        self.assertEqual(publish(s, V, dump(OLD)), rev)
        self.assertEqual(s.uploads, [])
        self.assertEqual(s.body(f"versions/{V}/manifest.json"), first)

    def test_a_backfill_leaves_the_old_revision_alone(self):
        s = Store()
        old = publish(s, V, dump(OLD))
        new = publish(s, V, dump(NEW))
        self.assertNotEqual(old, new)
        self.assertEqual(s.objects[f"revisions/{V}/{old}/items.parquet"][0], b"old items")
        self.assertEqual(s.body(f"versions/{V}/manifest.json")["revision"], new)

    def test_stopped_upload_keeps_the_old_revision_then_resumes(self):
        s = Store()
        old = publish(s, V, dump(OLD))
        s.fail_after = 1  # one file lands, then the run stops
        with self.assertRaises(RuntimeError):
            publish(s, V, dump(NEW))
        self.assertEqual(s.body(f"versions/{V}/manifest.json")["revision"], old)
        s.fail_after = None
        s.uploads.clear()
        new = publish(s, V, dump(NEW))
        self.assertEqual(len(s.uploads), 1)  # only the file the stopped run missed
        self.assertEqual(s.body(f"versions/{V}/manifest.json")["revision"], new)

    def test_stopped_before_the_pointer_resumes(self):
        s = Store()
        s.fail_after = len(NEW) + 1  # every revision file and its manifest land, then the run stops
        with self.assertRaises(RuntimeError):
            publish(s, V, dump(NEW))
        self.assertNotIn(f"versions/{V}/manifest.json", s.objects)
        s.fail_after = None
        s.uploads.clear()
        rev = publish(s, V, dump(NEW))
        self.assertEqual(s.uploads, [])
        self.assertEqual(s.body(f"versions/{V}/manifest.json")["revision"], rev)

    def test_drop_copies_keeps_a_version_its_revision_does_not_hold(self):
        s = Store()
        rev = publish(s, V, dump(OLD))
        legacy = "30260401_0"  # published before revisions: copies and a manifest without base
        s.objects[f"versions/{legacy}/items.parquet"] = (b"x", {})
        s.objects[f"versions/{legacy}/manifest.json"] = (json.dumps({"version": legacy, "files": {"items.parquet": {"sha256": "1"}}}).encode(), {})
        s.objects[f"versions/{V}/items.parquet"] = (b"old items", {})  # a copy publish once wrote
        s.objects[f"versions/{V}/items.meta.json"] = (b"{}", {})
        with mock.patch.dict(os.environ, {"BUCKET": "test"}), mock.patch.object(r2_upload, "_client", return_value=s):
            self.assertEqual(r2_upload.drop_copies(dry_run=True), 2)
            self.assertIn(f"versions/{V}/items.parquet", s.objects, "a dry run deletes nothing")
            del s.objects[f"revisions/{V}/{rev}/items.meta.json"]
            self.assertEqual(r2_upload.drop_copies(dry_run=False), 0, "the revision lacks a file: keep the copies")
            s.objects[f"revisions/{V}/{rev}/items.meta.json"] = (b"{}", {"sha256": hashlib.sha256(b"{}").hexdigest()})
            self.assertEqual(r2_upload.drop_copies(dry_run=False), 2)
        self.assertEqual(sorted(k for k in s.objects if k.startswith("versions/")),
                         [f"versions/{legacy}/items.parquet", f"versions/{legacy}/manifest.json", f"versions/{V}/manifest.json"])

    def test_revision_names_the_bytes_not_the_order(self):
        a = {"a": {"sha256": "1"}, "b": {"sha256": "2"}}
        b = {"b": {"sha256": "2"}, "a": {"sha256": "1"}}
        self.assertEqual(r2_upload.revision_of(a), r2_upload.revision_of(b))
        self.assertNotEqual(r2_upload.revision_of(a), r2_upload.revision_of({**a, "b": {"sha256": "3"}}))


if __name__ == "__main__":
    unittest.main()
