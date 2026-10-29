import json

from mnemos import evidence_ledger


def _write_ledger(path, entries):
    path.write_text("".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\\n" for item in entries), encoding="utf-8")


def test_export_and_verify_empty_ledger_anchor(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(evidence_ledger, "LEDGER_PATH", ledger)
    anchor_path = tmp_path / "mnemos-ledger-anchor.json"

    exported = evidence_ledger.export_anchor(anchor_path)
    verified = evidence_ledger.verify_anchor(anchor_path)

    assert exported["ledger_length"] == 0
    assert exported["head_hash"] == evidence_ledger.GENESIS
    assert verified["ok"] is True
    assert verified["status"] == "match"


def test_anchor_detects_truncation_and_head_rewrite(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(evidence_ledger, "LEDGER_PATH", ledger)
    entries = [
        {"sequence": 1, "entry_hash": "a" * 64},
        {"sequence": 2, "entry_hash": "b" * 64},
    ]
    _write_ledger(ledger, entries)
    anchor_path = tmp_path / "anchor.json"
    evidence_ledger.export_anchor(anchor_path)

    _write_ledger(ledger, entries[:1])
    truncated = evidence_ledger.verify_anchor(anchor_path)
    assert truncated["ok"] is False
    assert truncated["status"] == "mismatch"
    assert any("length mismatch" in error for error in truncated["errors"])

    entries[1]["entry_hash"] = "c" * 64
    _write_ledger(ledger, entries)
    rewritten = evidence_ledger.verify_anchor(anchor_path)
    assert rewritten["ok"] is False
    assert any("head hash" in error for error in rewritten["errors"])


def test_anchor_rejects_malformed_schema(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(evidence_ledger, "LEDGER_PATH", ledger)
    anchor_path = tmp_path / "anchor.json"
    anchor_path.write_text(json.dumps({"head_hash": "not-a-hash", "ledger_length": True}), encoding="utf-8")

    result = evidence_ledger.verify_anchor(anchor_path)
    assert result["ok"] is False
    assert result["status"] == "unknown"
