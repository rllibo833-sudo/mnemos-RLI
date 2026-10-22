import io
import json
import tempfile
import unittest
from pathlib import Path

from mnemos.mcp_server import call_tool, handle_message, serve
from mnemos.store import MemoryStore


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name) / "memory.sqlite3")
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_initialize_and_tool_discovery(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            self.store,
        )
        self.assertEqual(response["result"]["serverInfo"]["name"], "mnemos")
        self.assertIn("tools", response["result"]["capabilities"])

        tools = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.store)
        names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertEqual(names, {"mnemos_search", "mnemos_add", "mnemos_get", "mnemos_list", "mnemos_link", "mnemos_export"})

    def test_tools_round_trip(self):
        added = call_tool(self.store, "mnemos_add", {
            "content": "Parser rejects empty input", "kind": "fact", "tags": ["parser"]
        })
        self.assertEqual(call_tool(self.store, "mnemos_get", {"memory_id": added["id"]})["content"], added["content"])
        self.assertEqual(call_tool(self.store, "mnemos_search", {"query": "parser"})[0]["id"], added["id"])
        self.assertEqual(call_tool(self.store, "mnemos_list", {})[0]["id"], added["id"])

        other = self.store.add("Validate before parsing", kind="solution")
        link = call_tool(self.store, "mnemos_link", {
            "source_id": added["id"], "target_id": other["id"], "relation": "fixed_by"
        })
        self.assertEqual(link["relation"], "fixed_by")
        snapshot = call_tool(self.store, "mnemos_export", {})
        self.assertEqual(len(snapshot["memories"]), 2)
        self.assertEqual(len(snapshot["links"]), 1)

    def test_tool_errors_are_reported(self):
        with self.assertRaises(ValueError):
            call_tool(self.store, "mnemos_add", {"content": " "})
        with self.assertRaises(ValueError):
            call_tool(self.store, "mnemos_search", {"query": "x", "limit": True})
        response = handle_message({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "mnemos_get", "arguments": {"memory_id": "missing"}},
        }, self.store)
        self.assertTrue(response["result"]["isError"])

    def test_stdio_json_rpc_loop(self):
        incoming = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "",
        ])
        output = io.StringIO()
        self.assertEqual(serve(io.StringIO(incoming), output, self.db_path), 0)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2])


if __name__ == "__main__":
    unittest.main()
