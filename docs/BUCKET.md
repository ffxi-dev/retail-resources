# FFXI Resources — Bucket Layout

Public S3-compatible bucket for FFXI client data dumps. Mirrors every release published to [GitHub Releases](https://github.com/ffxi-dev/retail-resources/releases) and is the recommended fetch source for automated consumers.

**Base URL:** `https://ffxi-resources.sruon.dev`

No auth required. CORS allows browser access.

## Layout

```
ffxi-resources.sruon.dev/
├── versions.json                       # top-level index of all versions
├── revisions/
│   └── <version>/<revision>/           # one publish of a version; never rewritten
│       ├── manifest.json
│       └── <same files as below>
└── versions/
    └── <version>/                      # one directory per FFXI client version
        ├── manifest.json               # what's in this version, and its current revision
        ├── items.parquet
        ├── items.ndjson.gz
        ├── items.meta.json
        ├── items.schema.json
        ├── strings.parquet
        ├── strings.ndjson.gz
        ├── strings.meta.json
        ├── entities.{parquet,ndjson.gz,meta.json}
        ├── autotranslate.{parquet,ndjson.gz,meta.json}
        ├── spells.{parquet,ndjson.gz,meta.json}
        ├── abilities.{parquet,ndjson.gz,meta.json}
        ├── zones.{parquet,ndjson.gz,meta.json}
        ├── events.{parquet,ndjson.gz,meta.json}
        ├── events_actors.{parquet,ndjson.gz,meta.json}
        ├── events_scripts.parquet
        └── client_tables.{json,meta.json}
```

Schema for each artifact: see [docs/FORMATS.md](FORMATS.md).

## `versions.json`

Top-level index. Updated on every successful release.

```json
{
  "latest": "30260401_0",
  "versions": [
    {
      "version": "30260301_0",
      "revision": "3f9c0a1b2d4e",
      "published_at": "2026-04-15T07:42:11+00:00",
      "manifest": "versions/30260301_0/manifest.json",
      "file_count": 32
    },
    {
      "version": "30260401_0",
      "revision": "8c1a0c580d71",
      "published_at": "2026-05-01T06:12:33+00:00",
      "manifest": "versions/30260401_0/manifest.json",
      "file_count": 32
    }
  ]
}
```

| Field | Notes |
|---|---|
| `latest` | The most recent version string |
| `versions[]` | Sorted ascending by `version` |
| `versions[].version` | FFXI client version tag (e.g. `30260401_0`) |
| `versions[].revision` | The version's current revision; absent for a version not republished since revisions began |
| `versions[].published_at` | UTC ISO 8601 timestamp |
| `versions[].manifest` | Relative path to the per-version manifest |
| `versions[].file_count` | Number of artifact files in this version |

Cache-Control: 60 seconds.

## `versions/<version>/manifest.json`

Per-version listing with size and SHA-256 for every artifact, and the revision they belong to. Use this to verify integrity after download.

```json
{
  "version": "30260401_0",
  "revision": "8c1a0c580d71",
  "base": "revisions/30260401_0/8c1a0c580d71/",
  "generated_at": "2026-05-01T06:12:33+00:00",
  "source": {
    "commit": "95a8618…",
    "packages": { "xi-events": "git 1a2b3c…", "xi-tinkerer": "0.1.0", "pyarrow": "18.1.0" }
  },
  "files": {
    "items.parquet": {
      "size": 25184733,
      "sha256": "a3f1e0...c4d7"
    },
    "items.ndjson.gz": {
      "size": 19842117,
      "sha256": "b8c2..."
    }
  }
}
```

Cache-Control: 300 seconds.

| Field | Notes |
|---|---|
| `revision` | First 12 hex digits of the SHA-256 of the sorted `<file> <sha256>` lines. Same bytes, same revision |
| `base` | Where this revision's files live. Read files from here to get a set that never changes under you |
| `source` | The retail-resources commit and generator versions that produced it |

A version is republished when its data is corrected (a backfill). Each publish writes a new revision, checks every file, and only then rewrites this manifest, so the manifest never names a half-uploaded revision. Older manifests have no `revision`, `base` or `source`.

## Revisions and artifact files

`revisions/<version>/<revision>/` holds one publish: the files and the manifest. They are never rewritten. Cache-Control: one year, `immutable`. Key any cache on the revision, not the version.

`versions/<version>/<file>` holds a copy of the current revision's files, for readers that predate revisions. A republish rewrites them in place, so a reader can see old and new files mixed for a few minutes. Cache-Control: 300 seconds.

## Common access patterns

### Fetch the latest version directly via DuckDB

```sql
-- Resolve latest, then query items.parquet over HTTPS
WITH latest AS (
  SELECT json_extract_string(json, '$.latest') AS v
  FROM read_text('https://ffxi-resources.sruon.dev/versions.json') AS t(json)
)
SELECT id, name.english, weapon.damage
FROM read_parquet('https://ffxi-resources.sruon.dev/versions/' || (SELECT v FROM latest) || '/items.parquet')
WHERE category = 'weapon' AND weapon.damage > 50;
```

### Pin to a specific version

```
GET https://ffxi-resources.sruon.dev/versions/30260401_0/items.parquet
GET https://ffxi-resources.sruon.dev/versions/30260401_0/manifest.json
```

### Discover versions

```
GET https://ffxi-resources.sruon.dev/versions.json
```

### Verify integrity

```sh
curl -s https://ffxi-resources.sruon.dev/versions/30260401_0/manifest.json \
  | jq -r '.files["items.parquet"].sha256'
sha256sum items.parquet
```

## Release cadence

A new version is published whenever the FFXI client ships an update — typically a few times per month. The hourly sync publishes to R2 first, then the GitHub release, and tries again each hour until both have it. Monitor `versions.json.latest` or subscribe to GitHub Releases via the [release notifier app](https://github.com/apps/ffxi-resources-release-notifier).
