"""Stable public API for Mnemos' local-first runtime.

Implementation modules remain import-compatible for existing CLI and MCP
entry points. This facade gathers supported contracts in one package surface.
"""
from .contract import Change, GraphStore, Membership, Provenance, Workspace
from .store import MemoryStore
from .analysis import analyze_graph
from .device_mapper import collect_device_map
from .evolution import evolve_graph
from .forensics import reconstruct_case
from .graph import graph_payload, render_graph
from .integrity import (
    FINDING_STATUSES,
    compare_snapshot_histories,
    snapshot_artifact_map,
    snapshot_is_complete,
    snapshot_order_key,
    snapshot_scan,
    snapshot_scope,
    snapshot_scope_identity,
    would_create_cycle,
)
from .daemon import run_daemon
from .live_graph import make_handler, serve_live_graph
from .mcp_server import call_tool, handle_message, serve as serve_mcp

__version__ = "0.1.0"

__all__ = [
    "Change", "FINDING_STATUSES", "GraphStore", "Membership", "MemoryStore",
    "Provenance", "Workspace", "analyze_graph", "call_tool", "collect_device_map",
    "compare_snapshot_histories", "evolve_graph", "graph_payload", "handle_message",
    "make_handler", "reconstruct_case", "render_graph", "run_daemon",
    "serve_live_graph", "serve_mcp", "snapshot_artifact_map", "snapshot_is_complete",
    "snapshot_order_key", "snapshot_scan", "snapshot_scope", "snapshot_scope_identity",
    "would_create_cycle",
]
