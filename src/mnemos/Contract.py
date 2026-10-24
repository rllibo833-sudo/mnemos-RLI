"""Shared Graph Contract - Mnemos Living Knowledge Graph"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Dict, List, Optional
import time, uuid

Op = Literal["upsert", "delete"]
EntityType = Literal["memory", "link", "node", "relation"]
Verification = Literal["inferred", "verified", "contradicted"]
Visibility = Literal["private", "shared", "public"]
Role = Literal["reader", "writer", "admin"]

@dataclass
class Provenance:
    actor: str
    source: str
    created_at: float = field(default_factory=time.time)
    verification: Verification = "inferred"
    def to_dict(self): return asdict(self)

@dataclass
class Change:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = "default"
    entity_type: EntityType = "memory"
    entity_id: str = ""
    op: Op = "upsert"
    payload: Dict[str, Any] = field(default_factory=dict)
    lamport_clock: int = 0
    actor: str = ""
    timestamp: float = field(default_factory=time.time)

@dataclass
class Workspace:
    id: str
    visibility: Visibility = "private"
    created_at: float = field(default_factory=time.time)

@dataclass
class Membership:
    workspace_id: str
    user_id: str
    role: Role = "reader"

class GraphStore(ABC):
    @abstractmethod
    def get(self, memory_id: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def traverse_neighbors(self, node_id: str, depth: int = 1) -> Dict[str, Any]: ...
    @abstractmethod
    def traverse_path(self, src: str, dst: str, max_depth: int = 4) -> Optional[List[Dict[str, Any]]]: ...
    @abstractmethod
    def apply_change(self, change: Change) -> Dict[str, Any]: ...
    @abstractmethod
    def push(self, since_lamport: int = 0, workspace_id: str = "default") -> List[Change]: ...
    @abstractmethod
    def pull(self, changes: List[Change]) -> Dict[str, int]: ...
