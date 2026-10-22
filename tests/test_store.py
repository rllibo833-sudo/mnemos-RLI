import tempfile
import unittest
from pathlib import Path
from mnemos.store import MemoryStore
from mnemos.graph import render_graph

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
    def test_import_rejects_unknown_format(self):
        with self.assertRaises(ValueError): self.store.import_data({'format':'unknown'})
    def test_graph_contains_actual_records(self):
        a=self.store.add('A known decision',kind='decision'); b=self.store.add('A recorded solution',kind='solution')
        self.store.link(a['id'],b['id'],relation='leads_to'); output=Path(self.temp.name)/'graph.html'
        render_graph(self.store.list(),self.store.links(),output); html=output.read_text(encoding='utf-8')
        self.assertIn(a['id'],html); self.assertIn(b['id'],html); self.assertIn('leads_to',html)
        self.assertIn('MNEMOS / MEMORY GRAPH',html)

if __name__ == '__main__': unittest.main()
