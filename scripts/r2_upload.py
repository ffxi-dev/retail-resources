"""Publish dumps to R2, used by sync.yml and backfill.yml. Layout: docs/BUCKET.md.

Two subcommands:

  publish <version> <dist_dir>
    Uploads <dist_dir> as an immutable revision under revisions/<version>/<revision>/, checks every
    file, copies them to versions/<version>/ for readers of the old layout, and writes
    versions/<version>/manifest.json last. A rerun skips files already there, so a stopped
    publish resumes. Safe to run in parallel for different versions.

  rebuild-index
    Lists versions/*/manifest.json on the bucket, reads each, and writes a
    fresh versions.json to the bucket root. Idempotent; reflects whatever
    is currently in the bucket. Run once after a batch of uploads. If any
    manifest cannot be read or parsed, it fails and leaves versions.json
    as it was.

  published <version>
    Exits 0 when versions/<version>/manifest.json exists, 1 when it does not.

Reads the same env vars as the workflow steps:
  ENDPOINT, BUCKET, R2_KEY_ID, R2_APP_KEY; GITHUB_SHA when set
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

IMMUTABLE = "public, max-age=31536000, immutable"
SHORT = "public, max-age=300"
GENERATORS = ("xi-events", "xi-tinkerer", "pyarrow")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["ENDPOINT"],
        aws_access_key_id=os.environ["R2_KEY_ID"],
        aws_secret_access_key=os.environ["R2_APP_KEY"],
        region_name="auto",
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _package(name: str) -> str | None:
    """A generator's version, or its git commit when installed from git."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    commit = json.loads(dist.read_text("direct_url.json") or "{}").get("vcs_info", {}).get("commit_id")
    return f"git {commit}" if commit else dist.version


def revision_of(files: dict) -> str:
    lines = "".join(f"{name} {info['sha256']}\n" for name, info in sorted(files.items()))
    return hashlib.sha256(lines.encode()).hexdigest()[:12]


def _head(s3, bucket: str, key: str) -> dict | None:
    """The object's metadata, or None when it does not exist."""
    try:
        return s3.head_object(Bucket=bucket, Key=key).get("Metadata", {})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def _stored_sha256(s3, bucket: str, key: str) -> str | None:
    return (_head(s3, bucket, key) or {}).get("sha256")


def publish(version: str, dist_dir: Path) -> str:
    bucket = os.environ["BUCKET"]
    s3 = _client()

    files = {p.name: {"size": p.stat().st_size, "sha256": _sha256(p)} for p in sorted(dist_dir.iterdir()) if p.is_file()}
    if not files:
        raise SystemExit(f"{dist_dir} is empty; nothing to publish")
    revision = revision_of(files)
    base = f"revisions/{version}/{revision}/"
    manifest = {
        "version": version,
        "revision": revision,
        "base": base,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"commit": os.environ.get("GITHUB_SHA"), "packages": {n: _package(n) for n in GENERATORS}},
        "files": files,
    }

    uploaded = 0
    for name, info in files.items():
        key = base + name
        if _stored_sha256(s3, bucket, key) == info["sha256"]:
            continue
        print(f"  PUT {key}", flush=True)
        s3.upload_file(str(dist_dir / name), bucket, key, ExtraArgs={"CacheControl": IMMUTABLE, "Metadata": {"sha256": info["sha256"]}})
        if _stored_sha256(s3, bucket, key) != info["sha256"]:
            raise SystemExit(f"{key} does not match its hash after upload")
        uploaded += 1

    # The revision's manifest is written once; a rerun points the version at that same manifest.
    if _head(s3, bucket, base + "manifest.json") is None:
        body = json.dumps(manifest, indent=2).encode()
        s3.put_object(Bucket=bucket, Key=base + "manifest.json", Body=body, ContentType="application/json", CacheControl=IMMUTABLE)
    else:
        body = s3.get_object(Bucket=bucket, Key=base + "manifest.json")["Body"].read()

    # Copies for readers of the old layout. They are rewritten in place, so those readers can still
    # see a mix mid-publish; they go once every consumer reads `base`.
    for name, info in files.items():
        s3.copy_object(
            Bucket=bucket,
            Key=f"versions/{version}/{name}",
            CopySource={"Bucket": bucket, "Key": base + name},
            MetadataDirective="REPLACE",
            CacheControl=SHORT,
            Metadata={"sha256": info["sha256"]},
        )
    s3.put_object(Bucket=bucket, Key=f"versions/{version}/manifest.json", Body=body, ContentType="application/json", CacheControl=SHORT)
    print(f"Published {version} as revision {revision}: {uploaded} of {len(files)} files uploaded", flush=True)
    return revision


def published(version: str) -> bool:
    return _head(_client(), os.environ["BUCKET"], f"versions/{version}/manifest.json") is not None


def rebuild_index() -> None:
    bucket = os.environ["BUCKET"]
    s3 = _client()

    # List every versions/*/manifest.json
    paginator = s3.get_paginator("list_objects_v2")
    manifest_keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix="versions/"):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            if key.endswith("/manifest.json"):
                manifest_keys.append(key)

    # Publish only an index built from every manifest: skipping one that failed
    # to read would hide that release from res and Theater until the next rebuild.
    versions = []
    for key in manifest_keys:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            m = json.loads(obj["Body"].read())
            versions.append({
                "version": m["version"],
                "revision": m.get("revision"),
                "published_at": m.get("generated_at"),
                "manifest": key,
                "file_count": len(m.get("files", {})),
            })
        except (ClientError, ValueError, KeyError, TypeError) as e:
            raise SystemExit(f"Cannot read {key}: {e!r}; versions.json left unchanged") from e

    versions.sort(key=lambda v: v["version"])
    index = {
        "versions": versions,
        "latest": versions[-1]["version"] if versions else None,
    }
    s3.put_object(
        Bucket=bucket,
        Key="versions.json",
        Body=json.dumps(index, indent=2).encode(),
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )
    print(f"Rebuilt versions.json: {len(versions)} versions, latest={index['latest']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("publish", help="Publish one version's dump as a revision")
    up.add_argument("version")
    up.add_argument("dist_dir")

    sub.add_parser("rebuild-index", help="Rebuild top-level versions.json")

    check = sub.add_parser("published", help="Exit 0 when R2 has the version's manifest")
    check.add_argument("version")

    args = parser.parse_args()
    if args.cmd == "publish":
        publish(args.version, Path(args.dist_dir))
    elif args.cmd == "rebuild-index":
        rebuild_index()
    elif args.cmd == "published":
        sys.exit(0 if published(args.version) else 1)


if __name__ == "__main__":
    main()
