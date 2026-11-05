# Source intake for the canonical graph

The canonical graph may index project repositories, documents, photos, videos, audio, and Notion pages. Each imported item should retain its stable source identity, observation date, content hash where appropriate, extraction method, and a link to the related project or idea.

## Keep source material under its owner’s control

- Do not commit original private files or media to this public repository.
- Store only the smallest useful derived record: title, safe summary, source reference, selected metadata, and explicit graph links.
- Keep private originals on the device or in their existing service. Use a local-only reference when a public URL would disclose access or identity.
- For photos and videos, extract only user-approved metadata, OCR/transcript, selected-frame notes, and hashes. Never upload original media by default.
- For Notion, use an explicit export or authorized connector. Preserve page IDs and URLs only when safe to publish; otherwise use local aliases and keep the mapping private.
- Do not scan an entire device or workspace implicitly. Imports must have a named folder, selected files, or explicitly selected Notion pages.

## Suggested capture record

Use the existing node fields: `source.type`, `source.uri`, `source.filename`, `source.content_sha256`, `source.extraction_method`, `source.observed_at`, and `media` metadata. Put a concise text representation in `content`; keep binary payloads outside the graph. Link the source node to one or more project, topic, or decision nodes with a relation that explains the connection.

## Intake status

The `project-portfolio-rllibo833-sudo` node currently indexes public GitHub repositories only. File, photo, video, and Notion collections have not yet been imported. Add them in scoped batches and review the resulting records before publishing this public branch.
