"""Git-like tree history data (ADR-015)."""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

log = logging.getLogger("pig_t3.history_tree")


@dataclass
class HistoryNode:
    id: str
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    action_summary: str = ""
    source: str = "editor"
    status: str = "applied"
    files: list[str] = field(default_factory=list)
    applied_at: str = ""


class HistoryTreeManager:
    def __init__(self, root_folder: str):
        self._root = os.path.abspath(root_folder)
        self._path = os.path.join(
            self._root, ".pig", "history_tree.json"
        )
        self.nodes: dict[str, HistoryNode] = {}
        self.current: str | None = None
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("history tree load failed: %s", e)
            return
        self.current = data.get("current")
        for nid, nd in data.get("nodes", {}).items():
            if not isinstance(nd, dict):
                continue
            kwargs = {
                k: v for k, v in nd.items()
                if k in HistoryNode.__dataclass_fields__ and k != "id"
            }
            self.nodes[nid] = HistoryNode(id=nid, **kwargs)

    def save(self) -> None:
        try:
            os.makedirs(
                os.path.dirname(self._path), exist_ok=True
            )
            payload = {
                "current": self.current,
                "nodes": {
                    nid: asdict(n) for nid, n in self.nodes.items()
                },
            }
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.warning("history tree save failed: %s", e)

    def apply(
        self,
        action_summary: str,
        files: list[str],
        source: str = "editor",
        backup_id: str | None = None,
    ) -> str:
        nid = backup_id or str(uuid.uuid4())
        node = HistoryNode(
            id=nid,
            parent=self.current,
            action_summary=action_summary,
            source=source,
            files=list(files),
            status="applied",
            applied_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.nodes[nid] = node
        if self.current and self.current in self.nodes:
            self.nodes[self.current].children.append(nid)
        self.current = nid
        self.save()
        return nid

    def undo(self) -> HistoryNode | None:
        if not self.current or self.current not in self.nodes:
            return None
        node = self.nodes[self.current]
        if node.parent is None:
            return None
        node.status = "rolled_back"
        self.current = node.parent
        self.save()
        return node

    def redo(self) -> HistoryNode | None:
        if not self.current or self.current not in self.nodes:
            return None
        candidates = [
            self.nodes[c]
            for c in self.nodes[self.current].children
            if c in self.nodes
            and self.nodes[c].status == "rolled_back"
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda n: n.applied_at)
        nxt = candidates[-1]
        nxt.status = "applied"
        self.current = nxt.id
        self.save()
        return nxt

    def branch_from(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.current = node_id
            self.save()
