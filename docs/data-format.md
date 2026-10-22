# Mnemos Export Format v1

Exports are UTF-8 JSON with this top-level shape:

- `format`: exact version string `mnemos-export-v1`
- `exported_at`: UTC timestamp
- `memories`: array of memory objects
- `links`: array of relationship objects

## Memory object

- `id`: stable string identifier
- `content`: non-empty text
- `kind`: category such as `note`, `fact`, `decision`, or `solution`
- `tags`: array of strings
- `source`: optional source path or reference
- `metadata`: JSON object
- `created_at`, `updated_at`: ISO-8601 timestamps

## Link object

- `id`: stable string identifier
- `source_id`, `target_id`: IDs of existing memories
- `relation`: explicit relationship label, such as `resolved_by`
- `created_at`: ISO-8601 timestamp

## Import behavior

Imports are additive. Existing memory IDs and duplicate links are skipped. Links are imported only when both endpoints exist. Unknown format versions are rejected. Treat exports as user data and review them before importing into a trusted workspace.

This is an early format; a future incompatible change will use a new version identifier rather than silently changing v1 semantics.
