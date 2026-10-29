"""Signed append-only observation ledger for offline forensic provenance.

The JSONL ledger complements (does not replace) SQLite compatibility. Hash chaining
detects accidental edits and reordering; Ed25519 signatures authenticate entries only
while the private key remains trusted. A root-level attacker who can read this host's
private key can forge entries, so export/anchor the public key and ledger head elsewhere.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(os.environ.get("MNEMOS_EVIDENCE_LEDGER", Path.home() / ".mnemos" / "evidence-ledger.jsonl"))
KEY_PATH = Path(os.environ.get("MNEMOS_EVIDENCE_SIGNING_KEY", Path.home() / ".mnemos" / "keys" / "observations-ed25519.pem"))
GENESIS = "0" * 64


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return serialization, Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError("Signed evidence requires the 'cryptography' package; install mnemos-rli[war-mode].") from exc


def _load_or_create_key():
    serialization, Ed25519PrivateKey = _crypto()
    KEY_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if KEY_PATH.exists():
        raw = KEY_PATH.read_bytes()
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Evidence signing key is not Ed25519.")
        return key
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = KEY_PATH.with_suffix(".pub.pem")
    if not public_path.exists():
        public_path.write_bytes(public)
        try:
            os.chmod(public_path, 0o644)
        except OSError:
            pass
    return key


def _ledger_entries() -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    entries = []
    with LEDGER_PATH.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Evidence ledger line {line_number} is invalid JSON.") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Evidence ledger line {line_number} is not an object.")
            entries.append(item)
    return entries


def append_observation(observation: dict[str, Any], *, snapshot_id: str, war_mode: bool) -> dict[str, Any]:
    """Append and sign one observation; reject a ledger whose existing chain is broken."""
    report = verify_ledger()
    if not report["ok"]:
        raise ValueError("Refusing to append to invalid evidence ledger: " + "; ".join(report["errors"]))
    entries = _ledger_entries()
    previous = entries[-1]["entry_hash"] if entries else GENESIS
    payload = {
        "schema": "mnemos-signed-observation-v1",
        "sequence": len(entries) + 1,
        "previous_hash": previous,
        "snapshot_id": snapshot_id,
        "war_mode": bool(war_mode),
        "observation": observation,
    }
    entry_hash = hashlib.sha256(_canonical(payload)).hexdigest()
    key = _load_or_create_key()
    signature = base64.b64encode(key.sign(bytes.fromhex(entry_hash))).decode("ascii")
    entry = {
        **payload,
        "entry_hash": entry_hash,
        "signature": signature,
        "signature_algorithm": "Ed25519",
        "public_key_path": str(KEY_PATH.with_suffix(".pub.pem")),
    }
    LEDGER_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(LEDGER_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as stream:
        stream.write(_canonical(entry) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(LEDGER_PATH, 0o600)
    except OSError:
        pass
    return {"sequence": payload["sequence"], "entry_hash": entry_hash, "ledger": str(LEDGER_PATH)}


def verify_ledger() -> dict[str, Any]:
    """Verify chain links and Ed25519 signatures with the public key paired to the local key."""
    serialization, _ = _crypto()
    public_path = KEY_PATH.with_suffix(".pub.pem")
    try:
        entries = _ledger_entries()
    except (OSError, ValueError) as exc:
        return {"ok": False, "entries": 0, "errors": [str(exc)]}
    if not entries:
        return {"ok": True, "entries": 0, "head": GENESIS, "errors": []}
    if not public_path.exists():
        return {"ok": False, "entries": len(entries), "errors": ["Evidence public key is missing."]}
    try:
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
    except (OSError, ValueError) as exc:
        return {"ok": False, "entries": len(entries), "errors": [f"Cannot load evidence public key: {exc}"]}
    errors = []
    previous = GENESIS
    for expected_sequence, entry in enumerate(entries, 1):
        payload = {key: entry.get(key) for key in (
            "schema", "sequence", "previous_hash", "snapshot_id", "war_mode", "observation"
        )}
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        if entry.get("sequence") != expected_sequence:
            errors.append(f"Entry {expected_sequence}: sequence mismatch.")
        if entry.get("previous_hash") != previous:
            errors.append(f"Entry {expected_sequence}: previous hash mismatch.")
        if entry.get("entry_hash") != digest:
            errors.append(f"Entry {expected_sequence}: entry hash mismatch.")
        try:
            public_key.verify(base64.b64decode(entry["signature"], validate=True), bytes.fromhex(digest))
        except Exception:
            errors.append(f"Entry {expected_sequence}: Ed25519 signature invalid.")
        previous = str(entry.get("entry_hash") or "")
    return {"ok": not errors, "entries": len(entries), "head": previous, "errors": errors}
