# Output Formats

Every dump ships in two formats — pick whichever fits your pipeline:

- **`.ndjson.gz`** — gzipped newline-delimited JSON, one record per line. Streamable, jq-friendly, no schema upfront.
- **`.parquet`** — zstd-compressed columnar Parquet. DuckDB-native, predicate pushdown, smaller for repetitive data.

Both contain the same data. NDJSON has a sidecar `<name>.meta.json` with `version`/`schema_version`/`count`. Parquet embeds typing in the file itself.

## Conventions

- **One record per line/row**. No ID-keyed maps anywhere in record data.
- **Sorted output** for deterministic diffs and binary-searchable files.
- **Explicit nullability**: `null` for absent scalars, `[]` for absent arrays. Never omit.
- **Stable field order** within each record.
- **Sentinels left raw**: pseudo-entity IDs in `0x7FFFFFC0–0x7FFFFFF9` (e.g. `0x7FFFFFF0` LocalPlayer) appear as their integer values, not translated names. Consumers translate as needed.
- **Signed 16-bit interpretation** for event IDs: `-1` means `0xFFFF`, `-2` means `0xFFFE`. These are continuation/fragment markers in the FFXI event system.

## File index

| File | Description |
|---|---|
| `items.{ndjson.gz,parquet}` | Item records (one per item). Parquet uses wide schema with all category sub-objects nullable. |
| `items.schema.json` | JSON Schema for items |
| `strings.{ndjson.gz,parquet}` | Zone dialog strings (one string per row) |
| `entities.{ndjson.gz,parquet}` | Entity names (one entity per row) |
| `zones.{ndjson.gz,parquet}` | Zone names — long, alt (abbreviated), short (one zone per row) |
| `autotranslate.{ndjson.gz,parquet}` | Auto-translate phrases (one entry per row) |
| `keyitems.{ndjson.gz,parquet}` | Key items (one per row) |
| `events.{ndjson.gz,parquet}` | Event records — bytecode, decompiled Lua, and static analysis per event |
| `spells.{ndjson.gz,parquet}` | Spells (one spell per row) |
| `abilities.{ndjson.gz,parquet}` | Abilities + weapon skills (one per row) |
| `statuses.{ndjson.gz,parquet}` | Status effects — name, description, flag, icon |
| `pankration.{ndjson.gz,parquet}` | Pankration trait/modifier names |
| `merits.{ndjson.gz,parquet}` | Merit names |
| `augments.{ndjson.gz,parquet}` | Augment template strings |
| `monster_families.{ndjson.gz,parquet}` | Monster family names (singular + plural) |
| `mob_skills.{ndjson.gz,parquet}` | Mob skill names, by the id the action packet sends |
| `quests.{ndjson.gz,parquet}` | Quest names by log and id (one quest per row) |
| `missions.{ndjson.gz,parquet}` | Mission names by log and id (one mission per row) |
| `zone_layout.{ndjson.gz,parquet}` | RID sub-region entries — fishing areas, doors, zonelines, models, elevators, events (one per row) |
| `client_tables.json` | Lookup tables from `FFXiMain.dll`: which DAT holds a player's models and motions. One JSON object, not rows |

Plus a `<name>.meta.json` for each `.ndjson.gz`:

```json
{
  "version": "30260203_0",
  "schema_version": 1,
  "count": 28862
}
```

---

## items.ndjson.gz

Discriminated union via `category`. Sort: `(id)`. Schema also published as `items.schema.json` (Pydantic-generated JSON Schema).

```json
{
  "id": 16777,
  "resource_id": 12345,
  "name": {"english": "Death Scythe", "english_log_single": "...", "english_log_plural": "...", "japanese": "..."},
  "description": {"english": "...", "japanese": "..."},
  "type": "Weapon",
  "stack_size": 1,
  "flags": ["MysteryBox", "CanEquip"],
  "targets": [],
  "category": "weapon",
  "weapon": {
    "level": 73,
    "slots": ["Main"],
    "races": [...],
    "jobs": ["DRK"],
    "damage": 97,
    "delay": 528,
    "skill": "Scythe",
    ...
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Item ID |
| `resource_id` | int | Icon/model resource reference |
| `name.*`, `description.*` | string | Empty string `""` if absent |
| `type` | string | `Weapon`, `Armor`, `General`, `Furnishing`, etc. |
| `stack_size` | int | |
| `flags` | string[] | Decoded bitflags |
| `targets` | string[] | Valid target types |
| `category` | enum | `weapon` \| `armor` \| `usable` \| `furnishing` \| `puppet` \| `instinct` \| `slip` \| `monipulator` \| `general` |
| `<category>` | object | Category-specific fields (see schema) |

---

## strings.ndjson.gz

One row per zone string. Sort: `(zone_id, block, string_id)`. Schema version 2.

```json
{
  "zone_id": 100,
  "block": 0,
  "string_id": 42,
  "content": "Welcome, traveler."
}
```

| Field | Type | Notes |
|---|---|---|
| `zone_id` | int | Join against `zones.parquet` for the human-readable name |
| `block` | int | Zero-based block ordinal for this `(zone_id)`. Almost always `0`. A few zones (e.g. Aht Urhgan Whitegate phases) ship multiple string DATs whose IDs collide — each block has its own content |
| `string_id` | int | Index within the block's string DAT |
| `content` | string | Cleaned text. Placeholders: `<item>` `<keyitem>` `<player>` `<name>` `<number>` (POLUtils-style); `%` for ambiguous entity refs |

Primary key: `(zone_id, block, string_id)`.

---

## entities.ndjson.gz

One row per entity. Sort: `(zone_id, entity_id)`.

```json
{
  "zone_id": 230,
  "entity_id": 17104897,
  "name": "Valaineral R Davilles"
}
```

| Field | Type | Notes |
|---|---|---|
| `zone_id` | int | Join against `zones.parquet` for the human-readable name |
| `entity_id` | int | Server-side entity ID |
| `name` | string | Empty string preserved as-is |

---

## zones.ndjson.gz

One row per zone. Sort: `(id)`.

```json
{
  "id": 100,
  "name": "West Ronfaure",
  "name_alt": "W.Ronfaure",
  "name_short": "WRonfaure"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Zone ID |
| `name` | string | Full name (from `ROM/165/84.DAT`) |
| `name_alt` | string | Abbreviated name (from `ROM/165/83.DAT`) |
| `name_short` | string | Short name (from `ROM/165/85.DAT`) |

---

## keyitems.ndjson.gz

One row per key item. Sort: `(id)`.

```json
{
  "id": 100,
  "icon_id": 111,
  "category": 2,
  "name": "moon crystal",
  "name_plural": "moon crystals",
  "description": "\nThis is needed to pass through\nthe gate that only opens at a certain\ndate and time."
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Key item ID |
| `icon_id` | int | Icon resource reference |
| `category` | int | Category number (raw) |
| `name` / `name_plural` | string | Singular and plural display forms |
| `description` | string | Full description text |

---

## autotranslate.ndjson.gz

One row per phrase. Sort: `(category_name, entry_id)`.

```json
{
  "category_name": "Greetings",
  "entry_id": 1,
  "text": "Nice to meet you.",
  "key": "02020101"
}
```

| Field | Type | Notes |
|---|---|---|
| `category_name` | string | `Greetings`, `Spells`, `Job Abilities`, etc. |
| `entry_id` | int | Index within category |
| `text` | string | Raw display text. `@J{hex}` (job) and `@A{hex}` (zone) reference markers are preserved as-is for downstream resolvers |
| `key` | string | 4-byte hex sequence for the wire-format reference |

---

## events.ndjson.gz / events.parquet

One row per event. Sort: `(zone_id, actor_id, block, idx)`. Schema version 3.

Single self-contained file: raw bytecode, decompiled Lua, and static-analysis fields are all on the same row. Bytecode is per-event (no shared address space across events). Fragments (`event_id < 0`, ~71% of rows) carry bytecode but no Lua / analysis — fields are `null` / `[]` / `false` / `{}` for those.

```json
{
  "zone_id": 100,
  "actor_id": 16785749,
  "block": 0,
  "idx": 3,
  "event_id": 33,
  "entrypoint": 220,
  "byte_code": "4220011EF0FFFF7F1D0080231D0180...",
  "lua": "function event_33(npc, player, params)\n    ...\nend\n",
  "params": [0, 4, 5],
  "state": [10, 64],
  "scratch": [29, 30],
  "string_refs": [7468, 7469],
  "entities": [16785750, 16785789],
  "uses_result": true,
  "uses_result2": false,
  "imed": {"0": {"kind": "string", "value": 7468}, "1": {"kind": "string", "value": 7469}}
}
```

Primary key: `(zone_id, actor_id, block, idx)`.

| Field | Type | Notes |
|---|---|---|
| `zone_id` | int | Join against `zones.parquet` for the human-readable name |
| `actor_id` | int | Owning entity. Join against `entities.parquet` on `(zone_id, entity_id)` for the actor name. Sentinels (`0x7FFFFFC0–0x7FFFFFF9`) kept raw |
| `block` | int | Zero-based block ordinal for this `(zone_id, actor_id)`. A few zones (e.g. Aht Urhgan Whitegate phases) ship multiple event DATs that share an `actor_id` — each block has its own bytecode/imed |
| `idx` | int | Zero-based position within this block's events list. Disambiguates events that share an `event_id` (~47% of actors have duplicates) |
| `event_id` | int | Signed 16-bit. `-1` = `0xFFFF` fragment, `-2` = `0xFFFE`, etc. **Not unique within a block.** Fragments don't get decompiled |
| `entrypoint` | int | Byte offset within the actor block's concatenated bytecode region where this event's `byte_code` starts. Branch operands inside `byte_code` are absolute in that frame — disassemblers must rebase via `entrypoint` |
| `byte_code` | string | Hex string. The full bytecode slice for this single event (no `0x` prefix) |
| `lua` | string \| null | Decompiled Lua source produced via [xi-events-py](https://github.com/sruon/xi-events-py). `null` for fragments |
| `params` | int[] | Indices into `params[]` region this event reads/writes |
| `state` | int[] | State-region addresses touched (excluding result/result2) |
| `scratch` | int[] | Scratch-region addresses touched |
| `string_refs` | int[] | Sorted, deduped `string_id`s referenced. Join against `strings.parquet` |
| `entities` | int[] | Sorted, deduped real entity IDs referenced (sentinels filtered). Useful as a reverse index — `WHERE list_contains(entities, X)` |
| `uses_result` / `uses_result2` | bool | Whether the event reads/writes the `result` / `result2` slot |
| `imed` | map\<int, struct\<kind: string, value: int\>\> | Sparse: only slots this event consumes. `kind` ∈ `{string, item, ticks, ascii, bit}`. `value` is the resolved value already pulled from the actor's imed table — no join needed |

---

## spells.ndjson.gz / spells.parquet

One row per spell. Sort: `(id)`.

```json
{
  "id": 1,
  "index": 1,
  "name": "Cure",
  "description": "Restores target's HP. Afflatus Solace: Grants the effect of \"Stoneskin.\"",
  "type": "WhiteMagic",
  "element": "Light",
  "skill": "HealingMagic",
  "mp_cost": 8,
  "cast_time": 8,
  "recast_time": 20,
  "range": "D20",
  "aoe_range": "None",
  "area_shape": "Single",
  "icon_id": 6,
  "valid_targets": ["SelfTarget", "Player", "PartyMember", "Ally", "NPC", "Enemy"],
  "level_required": {"WHM": 1, "RDM": 3, "PLD": 5, "SCH": 5, "MON": 1}
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Spell ID |
| `index` | int | Index in MenuTable's Mgc_ section (used for name lookup) |
| `name` / `description` | string | From DmsgTable (ROM/181/73.DAT, ROM/181/75.DAT) |
| `type` | string | WhiteMagic, BlackMagic, BardSong, Geomancy, Ninjutsu, SummonerPact, BlueMagic, etc. |
| `element` | string | Fire, Ice, Wind, Earth, Lightning, Water, Light, Dark |
| `skill` | string | HealingMagic, ElementalMagic, etc. |
| `mp_cost` / `cast_time` / `recast_time` | int | |
| `range` / `aoe_range` | string | Distance enum (e.g. `D20`, `None`) |
| `area_shape` | string | Single, Sphere, Cone, CasterSphere, etc. |
| `icon_id` | int | |
| `valid_targets` | string[] | |
| `level_required` | object | Job → level map |

---

## abilities.ndjson.gz / abilities.parquet

One row per ability or weapon skill. Sort: `(id)`.

```json
{
  "id": 1,
  "name": "Combo",
  "description": "Delivers a threefold attack...",
  "type": "Weapon",
  "icon_id": 46,
  "mp_cost": 0,
  "tp_cost": -1,
  "range": "None",
  "aoe_range": "None",
  "area_shape": "Single",
  "shared_timer_id": 900,
  "valid_targets": ["Enemy"]
}
```

| Field                                | Type     | Notes                                                                                                                                                        |
|--------------------------------------|----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                                 | int      | Ability ID                                                                                                                                                   |
| `name` / `description`               | string   | From DmsgTable (ROM/181/72.DAT, ROM/181/74.DAT)                                                                                                              |
| `type`                               | string   | Weapon (weaponskill), Job, Trait, Monster, BloodPactRage, BloodPactWard, Corsair, Pet, Scholar, Waltz, Step, Samba, Jig, Flourish1/2/3, Effusion, Rune, etc. |
| `icon_id`                            | int      |                                                                                                                                                              |
| `mp_cost` / `tp_cost`                | int      | `tp_cost: -1` means N/A                                                                                                                                      |
| `range` / `aoe_range` / `area_shape` | string   | Same enum types as spells                                                                                                                                    |
| `shared_timer_id`                    | int      |                                                                                                                                                              |
| `valid_targets`                      | string[] |                                                                                                                                                              |

---

## statuses.ndjson.gz / statuses.parquet

One row per status effect. Sort: `(id)`. Joins display names from `StatusNames` with `StatusInfo` (description + icon).

```json
{
  "id": 1,
  "name": "weakness",
  "name_passive": "weakened",
  "description": "You have been knocked unconscious.",
  "flag": 65280,
  "icon": "<base64 BitmapA bytes>"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Status effect ID |
| `name` / `name_passive` | string | Active and passive form (e.g. "stun" / "stunned") |
| `description` | string | Full description text |
| `flag` | int | Raw bitfield from StatusInfo |
| `icon` | string (NDJSON) / bytes (Parquet) | FFXI BitmapA-tagged icon. NDJSON has it base64-encoded, Parquet has raw bytes. Decoded bytes start with `0x91` (BitmapA tag) followed by category/id text and a 32×32 8-bit paletted bitmap |

---

## pankration.ndjson.gz / pankration.parquet

Pankration trait/modifier names. Sort: `(id)`.

```json
{"id": 1, "name": "Main Job: Warrior"}
```

---

## merits.ndjson.gz / merits.parquet

Merit names + descriptions. The DAT stores name on the even ID and description on the next odd ID; this dumper pairs them and drops devname placeholders. Sort: `(id)`.

```json
{
  "id": 644,
  "name": "Ice Magic Accuracy",
  "description": "Increase the accuracy of Ice spells by 3."
}
```

---

## augments.ndjson.gz / augments.parquet

Augment template strings (printf-like with control codes the client expands at render time). Sort: `(id)`.

```json
{"id": 1, "text": "{FIR}%+d "}
```

---

## monster_families.ndjson.gz / monster_families.parquet

Monster family display names. Sort: `(id)`.

```json
{"id": 1, "name": "crab", "name_plural": "crabs"}
```

---

## mob_skills.ndjson.gz / mob_skills.parquet

Mob skill names from ROM/27/80.DAT. Sort: `(id)`. Entry `i` of the DAT is mob skill `256 + i`: the id the action packet (0x028, category 11) sends and LSB's `mob_skills` uses. Unused entries (`.`, `#123`) are left out.

```json
{"id": 257, "name": "Foot Kick"}
```

---

## quests.ndjson.gz / quests.parquet

Quest names from the client's quest log DATs, one per log. Sort: `(log_id, id)`. The id is the quest's bit in the log the 0x056 packet sends (port `0x50 + 8 * log_id` for quests under way, `0x90 + 8 * log_id` for quests done, for logs 0 to 7; Abyssea `0xE0`/`0xE8`, Adoulin `0xF0`/`0xF8`, Coalition `0x100`/`0x108`) and the id LSB uses. The log name comes from the client's menu text (ROM/165/76.DAT), cut before the colon ("Outlands: Current Quests"). Unused slots, which keep a Japanese placeholder name or an empty client line, are left out.

| log_id | log | DAT |
|---|---|---|
| 0 | San d'Oria | ROM/176/60.DAT |
| 1 | Bastok | ROM/176/61.DAT |
| 2 | Windurst | ROM/176/62.DAT |
| 3 | Jeuno | ROM/176/63.DAT |
| 4 | Other Areas | ROM/176/64.DAT |
| 5 | Outlands | ROM/176/65.DAT |
| 6 | Aht Urhgan | ROM/176/66.DAT |
| 7 | Crystal War | ROM/196/6.DAT |
| 8 | Abyssea | ROM/242/64.DAT |
| 9 | Adoulin | ROM/293/70.DAT |
| 10 | Coalition | ROM/293/71.DAT |

```json
{"log_id": 0, "log": "San d'Oria", "id": 110, "name": "Spice Gals", "repeatable": true, "description": "Client: Rouva (Victory Square,
 Southern San d'Oria)
Summary:
 ..."}
```

| Field | Type | Notes |
|---|---|---|
| `log_id` | int | The log, numbered as LSB's `xi.questLog` |
| `log` | string | The log's name in the client's menus |
| `id` | int | The quest within its log |
| `name` | string | Without the leading `+` the client writes before some names |
| `repeatable` | bool | The client writes `+` before the name: quests that can be done again (Trial by Earth, Eco-Warrior) |
| `description` | string | The quest log's text: client and summary, with the client's line breaks |

Primary key: `(log_id, id)`.

---

## missions.ndjson.gz / missions.parquet

Mission names from the client's mission log DATs, one per log. Sort: `(log_id, id)`. The id is the value the 0x056 packet sends: a bit index in the logs it keeps as bits (nation and Zilart missions done, ToAU and WotG, Campaign), else the current mission's number. Seekers of Adoulin and Rhapsodies of Vana'diel number from 110 as the packet does; LSB stores SoA as `(id - 110) / 2` and RoV as `id - 108`. Chains of Promathia and the later logs nest steps under chapters, written with `__` per level; a chapter that shares its first step's id gives way to the step. Placeholders are left out as for quests.

| log_id | log | DAT |
|---|---|---|
| 0 | San d'Oria | ROM/176/67.DAT |
| 1 | Bastok | ROM/176/68.DAT |
| 2 | Windurst | ROM/176/69.DAT |
| 3 | Rise of the Zilart | ROM/176/70.DAT |
| 4 | Treasures of Aht Urhgan | ROM/176/73.DAT |
| 5 | Wings of the Goddess | ROM/196/7.DAT |
| 6 | Chains of Promathia | ROM/176/71.DAT |
| 7 | Assault | ROM/176/72.DAT |
| 8 | Campaign | ROM/196/8.DAT |
| 9 | A Crystalline Prophecy | ROM/222/18.DAT |
| 10 | A Moogle Kupo d'Etat | ROM/223/12.DAT |
| 11 | A Shantotto Ascension | ROM/223/13.DAT |
| 12 | Seekers of Adoulin | ROM/293/69.DAT |
| 13 | Rhapsodies of Vana'diel | ROM/333/4.DAT |
| 14 | The Voracious Resurgence | ROM/364/36.DAT |

```json
{"log_id": 13, "log": "Rhapsodies of Vana'diel", "id": 110, "name": "Resonance", "depth": 1, "description": "Mission Orders:
 ..."}
```

| Field | Type | Notes |
|---|---|---|
| `log_id` | int | The log, numbered as LSB's `xi.mission.log_id` (TVR 14) |
| `log` | string | The log's name in the client's menus |
| `id` | int | The mission within its log |
| `name` | string | Without the `__` that nests it |
| `depth` | int | 0 for a chapter or a flat log's mission, 1 for a step, 2 for a step within a step |
| `description` | string | The mission orders, with the client's line breaks |

Primary key: `(log_id, id)`.

---

## client_tables.json

Lookup tables the client keeps in `FFXiMain.dll`'s `.data` section. They say which DAT file holds a player's equipment models and motions. Unlike every other artifact this is one JSON object, one key per table, because each table is a short array indexed by race. Sidecar: `client_tables.meta.json` (`count` is the number of tables).

```json
{
  "race_files": {"description": "...", "values": [7072, 7072, 10248, ...]},
  "battle_skirt": {"description": "...", "values": [[9800, 9928], [9800, 9928], ...]},
  ...
}
```

All values are file ids: resolve them through `FTABLE`/`VTABLE` to a `ROM*/dir/file.DAT` path.

**Race id** is the index into every `values` array: the race the look (GrapIDTbl) carries, 1 hume male, 2 hume female, 3 elvaan male, 4 elvaan female, 5 tarutaru male, 6 tarutaru female, 7 mithra, 8 galka; 29-31 the child NPCs and 32-36 the chocobos. Index 0 copies hume male. Most tables cover only 0-8.

**Skirt kind** comes from byte 9 of the body piece's info block (1 or 2). Each motion table has a `_skirt` partner: a `[kind 1, kind 2]` pair per race, plus the same offset as the main table, holding the motions for the skirt layer.

| Key | Size | File id |
|---|---|---|
| `race_files` | 37 u16 | First file of the race's model set. +0 skeleton and lower-body motions, +1 upper-body motions, +3 and +4 the skirt layer for skirt kinds 1 and 2. |
| `equipment` | 37 entries, null or 9 slots of `[first, count]` runs | Equipment model to file. Slots: 0 face, 1 head, 2 body, 3 hands, 4 legs, 5 feet, 6 main, 7 sub, 8 ranged. Model ids count on through the runs: model `m` is `first + m` in the first run with `m < count`, after subtracting the counts of the runs before it. Null for races 9-28. |
| `battle` | 9 u16 | Engaged motions with one hand armed: + the main weapon's motion type (byte 3 of its info block). |
| `dual_main` | 9 u16 | Engaged motions for the main hand when dual wielding: + main weapon motion type. |
| `dual_off` | 9 u16 | Engaged motions for the off hand when dual wielding: + off-hand weapon motion type. |
| `emote` | 9 u16 | Emotes: + emote id. |
| `weaponskill` | 9 u16 | Weapon skills (action category 3), animation id below 256: + animation id. |
| `weaponskill_high` | 9 u16 | Weapon skills, animation id 256 and up: + animation id − 256. |
| `dance` | 9 u16 | Dancer moves (action category 14): + animation id. |
| `rune_fencer` | 9 u32 | Rune Fencer moves (action category 15): + animation id. |
| `action` | 9 u16 | Other motions: + 1 fishing, + 4 sitting on a chair, + 5 riding a mount. |
| `fishing_rod` | 9 u16 | Fishing rods: + the ranged slot's model id. No skirt partner. |
| `<name>_skirt` | 9 pairs, same width as `<name>` | Skirt layer for each motion table above, by skirt kind. |

**How they are found.** Each table is located by its first values, as xim and the in-browser replay do: two equal entries for race 0 and 1 (`9672, 9672` for `battle`), `7072, 7072, 10248` for `race_files`, and the u32 run `7080, 32` (hume male faces) for `equipment`. A `_skirt` table starts at the next 4-byte boundary after its main table. The dump fails if an anchor matches zero or several times, or if a skirt table does not hold larger file ids than its main table.

**Across versions.** Every table except `equipment` is the same from the November 2022 build to October 2026; only the addresses move by a few bytes. `equipment` run counts grow when Square Enix adds models (hume male main-hand and sub run 4 went from 32 to 300 models between November 2022 and September 2025). A much older build, from before Dancer, has no `dance` table.

**What is confirmed.** In the October 2026 build, the client code reads `battle`, `dual_*`, `race_files` and their skirt pairs in one function (`0x100D2D70`/`0x100D2E30`), `weaponskill`, `weaponskill_high`, `dance` and `rune_fencer` by action category in `0x100D25E0`, `emote` in `0x100D1C80`, `action` in `0x100D2A10` and siblings, and `equipment` through a pointer per race at `0x1035F378`. The skirt kind and weapon motion type bytes are copied from the info block of the body and weapon models (`0x100D0B50`). The meanings of `action`'s offsets, `emote`'s index and `fishing_rod` come from xim and are not checked against the client.

---

## zone_layout.ndjson.gz / zone_layout.parquet

One row per RID sub-region entry. Sort: `(zone_id, idx)`. Field layout matches xiregiondump's `all_zones.json` byte-for-byte.

```json
{
  "zone_id": 9,
  "idx": 0,
  "type": "Elevator",
  "id_str": "@090",
  "target_id_str": "    ",
  "id": 809054272,
  "target_id": 538976288,
  "pos_x": 300.0, "pos_y": 13.4161, "pos_z": -60.0,
  "tex_map_no": 0,
  "ry": 0.0,
  "scale_x": 8.0, "scale_y": 50.0, "scale_z": 8.0,
  "zone_no": 9,
  "arrow_flag": 80,
  "lift_height_0": 4795,
  "lift_height_1": -3520,
  "lift_current_height": 0.0,
  "flag": 0,
  "file_id": null
}
```

| Field | Type | Notes |
|---|---|---|
| `zone_id` / `idx` | int | Composite primary key |
| `type` | enum | `ZoneLine` \| `Door` \| `FishingArea` \| `Elevator` \| `Event` \| `Model` \| `Unknown` (derived from first byte of `id_str`) |
| `id_str` / `target_id_str` | string | 4-byte ASCII identifiers; `target_id_str` paired endpoint for ZoneLines and Doors, mostly spaces otherwise |
| `id` / `target_id` | int | u32 view of the same bytes |
| `pos_x/y/z` | float | World coordinates |
| `tex_map_no` | int | Texture map index (mostly 0) |
| `ry` | float | Rotation around Y axis (radians) |
| `scale_x/y/z` | float | OBB half-extents (NOT radius) |
| `zone_no` | int | Polymorphic: Model → raw file id; ZoneLine → destination zone; otherwise 0 or unused |
| `arrow_flag` | int | Elevator/UI arrow flag |
| `lift_height_0` / `lift_height_1` | int (i16) | Elevator travel range |
| `lift_current_height` | float | Elevator initial position |
| `flag` | int | Door orientation / misc flag |
| `file_id` | int \| null | Resolved Model file id (`raw < 600 ? raw+100 : raw+83191` over `zone_no`); `null` for non-Model entries |

---

## DuckDB usage

Parquet is preferred — typed columns, predicate pushdown, no parsing overhead:

```sql
-- Load Parquet directly
CREATE TABLE events AS SELECT * FROM 'events.parquet';

-- Reverse lookup: events involving a specific entity
SELECT zone_id, actor_id, event_id, lua
FROM events WHERE list_contains(entities, 16785750) OR actor_id = 16785750;

-- Get bytecode + decompiled Lua for a specific event
SELECT byte_code, lua
FROM events
WHERE zone_id = 100 AND actor_id = 16785749 AND block = 0 AND idx = 3;

-- Find all events that read a specific string
SELECT zone_id, actor_id, event_id
FROM events WHERE list_contains(string_refs, 7468);

-- Items: query into category-specific fields (struct columns)
SELECT id, name.english, weapon.damage, weapon.delay
FROM 'items.parquet'
WHERE category = 'weapon' AND weapon.damage > 50;
```

Or use NDJSON if you want streaming/scripting:

```sql
CREATE TABLE events AS SELECT * FROM read_ndjson_auto('events.ndjson.gz');
```
