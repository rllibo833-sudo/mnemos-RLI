import tempfile
import unittest
from pathlib import Path
from mnemos.store import MemoryStore
from mnemos.graph import graph_payload, render_graph

class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp.name) / 'memory.sqlite3')
    def tearDown(self): self.temp.cleanup()
    def test_add_get_and_search(self):
        item = self.store.add('Parser rejects empty input', kind='fact', tags=['parser','bug'])
        self.assertEqual(self.store.get(item['id'])['content'], 'Parser rejects empty input')
        self.assertEqual(self.store.search('PARSER')[0]['id'], item['id'])
        self.assertEqual(self.store.search('not-present'), [])
    def test_rejects_empty_content(self):
        with self.assertRaises(ValueError): self.store.add('   ')
    def test_links(self):
        a=self.store.add('Decision A'); b=self.store.add('Solution B')
        self.assertEqual(self.store.link(a['id'],b['id'],relation='resolved_by')['relation'],'resolved_by')
        self.assertEqual(len(self.store.links(a['id'])),1)
        with self.assertRaises(ValueError): self.store.link(a['id'],a['id'])
        with self.assertRaises(KeyError): self.store.link(a['id'],'missing')
    def test_export_import_is_portable_and_idempotent(self):
        a=self.store.add('Remember this'); b=self.store.add('Related decision',kind='decision')
        self.store.link(a['id'],b['id']); payload=self.store.export_data()
        second=MemoryStore(Path(self.temp.name)/'second.sqlite3')
        self.assertEqual(second.import_data(payload),(2,1)); self.assertEqual(second.import_data(payload),(0,0))
        self.assertEqual(len(second.list()),2); self.assertEqual(len(second.links()),1)
    def test_export_includes_more_than_ten_thousand_memories_and_all_link_endpoints(self):
        # Seed directly to keep this scale regression test fast and focused on export completeness.
        count = 10001
        stamp = '2026-01-01T00:00:00+00:00'
        with self.store._connect() as db:
            db.executemany(
                """INSERT INTO memories
                (id, content, kind, tags_json, source, metadata_json, created_at, updated_at)
                VALUES (?, ?, 'note', '[]', NULL, '{}', ?, ?)""",
                ((f'memory-{i:05d}', f'memory content {i}', stamp, stamp) for i in range(count)),
            )
            db.execute(
                """INSERT INTO links (id, source_id, target_id, relation, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                ('link-oldest-newest', 'memory-00000', 'memory-10000', 'relates_to', stamp),
            )
        payload = self.store.export_data()
        self.assertEqual(len(payload['memories']), count)
        self.assertEqual(len(payload['links']), 1)
        self.assertTrue(MemoryStore.validate_export(payload)['ok'])

    def test_import_enqueues_only_new_imported_records(self):
        source = MemoryStore(Path(self.temp.name) / 'source.sqlite3')
        a = source.add('Imported fact')
        b = source.add('Imported decision', kind='decision')
        source.link(a['id'], b['id'], relation='supports')
        payload = source.export_data()

        target = MemoryStore(Path(self.temp.name) / 'target.sqlite3')
        self.assertEqual(target.import_data(payload), (2, 1))
        pending = target.pending_changes()
        self.assertEqual(len(pending), 3)
        self.assertEqual(
            sorted(change['entity_type'] for change in pending),
            ['link', 'memory', 'memory'],
        )
        self.assertTrue(all(change['operation'] == 'upsert' for change in pending))

        self.assertEqual(target.import_data(payload), (0, 0))
        self.assertEqual(len(target.pending_changes()), 3)

    def test_schema_version_one_is_upgraded_additively(self):
        legacy_path = Path(self.temp.name) / 'legacy.sqlite3'
        legacy = MemoryStore(legacy_path)
        memory = legacy.add('Preserve existing data')
        with legacy._connect() as db:
            db.execute("UPDATE mnemos_meta SET value = '1' WHERE key = 'schema_version'")
        upgraded = MemoryStore(legacy_path)
        self.assertEqual(upgraded.get(memory['id'])['content'], 'Preserve existing data')
        self.assertEqual(upgraded.sync_status()['schema_version'], 2)
        self.assertGreaterEqual(upgraded.sync_status()['outbox_total'], 1)

    def test_diagnostics_reports_healthy_local_database(self):
        self.store.add('Local-only diagnostic check')
        report = self.store.diagnostics()
        self.assertTrue(report['ok'])
        self.assertEqual(report['integrity_check'], ['ok'])
        self.assertEqual(report['foreign_key_violations'], [])
        self.assertEqual(report['memories'], 1)
        self.assertEqual(report['links'], 0)
        self.assertFalse(report['network_required'])

    def test_diagnostics_detects_foreign_key_violation(self):
        a = self.store.add('Existing memory')
        with self.store._connect() as db:
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute(
                "INSERT INTO links (id, source_id, target_id, relation, created_at) VALUES (?, ?, ?, ?, ?)",
                ('broken-link', a['id'], 'missing-target', 'relates_to', '2026-01-01T00:00:00+00:00')
            )
        report = self.store.diagnostics()
        self.assertFalse(report['ok'])
        self.assertEqual(len(report['foreign_key_violations']), 1)

    def test_validate_export_accepts_valid_export(self):
        a = self.store.add('Portable memory')
        b = self.store.add('Portable decision', kind='decision')
        self.store.link(a['id'], b['id'])
        report = MemoryStore.validate_export(self.store.export_data())
        self.assertTrue(report['ok'])
        self.assertEqual(report['memories'], 2)
        self.assertEqual(report['links'], 1)
        self.assertEqual(report['errors'], [])

    def test_validate_export_rejects_dangling_link_and_duplicate_id(self):
        payload = {
            'format': 'mnemos-export-v1',
            'memories': [
                {'id': 'same', 'content': 'one'},
                {'id': 'same', 'content': 'two'},
            ],
            'links': [{'source_id': 'same', 'target_id': 'missing', 'relation': 'related'}],
        }
        report = MemoryStore.validate_export(payload)
        self.assertFalse(report['ok'])
        self.assertTrue(any('Duplicate memory ID' in error for error in report['errors']))
        self.assertTrue(any('target_id' in error for error in report['errors']))

    def test_import_rejects_invalid_export_without_partial_changes(self):
        payload = {
            'format': 'mnemos-export-v1',
            'memories': [
                {'id': 'valid-id', 'content': 'Would otherwise be imported'},
                {'id': 'broken-id', 'content': '   '},
            ],
            'links': [],
        }
        with self.assertRaisesRegex(ValueError, 'Invalid Mnemos export'):
            self.store.import_data(payload)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.store.links(), [])

    def test_import_rejects_unknown_format(self):
        with self.assertRaises(ValueError): self.store.import_data({'format':'unknown'})
    def test_graph_payload_stats_and_edges_are_real_and_deduplicated(self):
        a = self.store.add('Graph decision', kind='decision')
        b = self.store.add('Graph agent', kind='agent')
        self.store.link(a['id'], b['id'], relation='uses')
        records = self.store.list_all()
        links = self.store.links()
        payload = graph_payload(records + [records[0]], links + [links[0], {
            'id': 'dangling', 'source_id': a['id'], 'target_id': 'missing', 'relation': 'uses'
        }])
        self.assertEqual(payload['stats']['memories'], 2)
        self.assertEqual(payload['stats']['nodes'], 2)
        self.assertEqual(payload['stats']['relationships'], 1)
        self.assertEqual(payload['stats']['agents'], 1)
        self.assertEqual(payload['stats']['kinds'], {'agent': 1, 'decision': 1})
        self.assertEqual(len(payload['links']), 1)

    def test_graph_json_cli_exports_canonical_graph_payload(self):
        from mnemos.cli import main
        import json
        a = self.store.add('JSON node A')
        b = self.store.add('JSON node B', kind='agent')
        self.store.link(a['id'], b['id'], relation='uses')
        output = Path(self.temp.name) / 'graph.json'
        self.assertEqual(main(['--db', str(self.store.path), 'graph', '--format', 'json',
                               '--output', str(output)]), 0)
        payload = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(payload['stats']['nodes'], 2)
        self.assertEqual(payload['stats']['relationships'], 1)
        self.assertEqual(payload['stats']['agents'], 1)
        self.assertEqual(len(payload['links']), 1)

    def test_graph_contains_actual_records(self):
        a=self.store.add('A known decision',kind='decision'); b=self.store.add('A recorded solution',kind='solution')
        self.store.link(a['id'],b['id'],relation='leads_to'); output=Path(self.temp.name)/'graph.html'
        render_graph(self.store.list(),self.store.links(),output); html=output.read_text(encoding='utf-8')
        self.assertIn(a['id'],html); self.assertIn(b['id'],html); self.assertIn('leads_to',html)
        self.assertIn('MNEMOS / MEMORY GRAPH',html)

if __name__ == '__main__': unittest.main()
