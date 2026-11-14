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
    payload: dict = field(default_factory=dict)


class HistoryTreeManager:
    """Data-layer для git-like дерева истории.

    max_nodes > 0 → soft cap: при превышении prune'ит старые rolled_back
    ноды (не предков current). Если prune'ить нечего (все на пути к
    current) — оставляет как есть.
    """

    def __init__(self, root_folder: str, max_nodes: int = 0):
        self._root = os.path.abspath(root_folder)
        self._path = os.path.join(
            self._root, ".pig", "history_tree.json"
        )
        self.max_nodes = max_nodes
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
            if "payload" in kwargs and not isinstance(
                kwargs["payload"], dict
            ):
                kwargs["payload"] = {}
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
        payload: dict | None = None,
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
            payload=dict(payload or {}),
        )
        self.nodes[nid] = node
        if self.current and self.current in self.nodes:
            self.nodes[self.current].children.append(nid)
        self.current = nid
        if self.max_nodes > 0 and len(self.nodes) > self.max_nodes:
            self._prune_internal()
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

    def delete_node(
        self, node_id: str, *, cascade: bool = False
    ) -> int:
        """Удалить ноду. cascade → удалить всё поддерево.

        Возвращает количество удалённых нод. Если удалили current —
        current сбрасывается на parent (или None).
        """
        if node_id not in self.nodes:
            return 0
        node = self.nodes[node_id]
        if node.children and not cascade:
            raise ValueError(
                f"У ноды {node_id!r} есть {len(node.children)} детей; "
                "используйте cascade=True"
            )
        removed = 0
        to_remove = [node_id]
        while to_remove:
            nid = to_remove.pop()
            n = self.nodes.pop(nid, None)
            if n is None:
                continue
            removed += 1
            to_remove.extend(n.children)
        parent_id = node.parent
        if parent_id and parent_id in self.nodes:
            children = self.nodes[parent_id].children
            if node_id in children:
                children.remove(node_id)
        if self.current not in self.nodes:
            self.current = (
                parent_id if parent_id in self.nodes else None
            )
        self.save()
        return removed

    def prune(self) -> int:
        """Публичный prune: удалить старые rolled_back ноды до max_nodes.

        Защищает current и всех его предков. Возвращает число удалённых.
        """
        if self.max_nodes <= 0 or len(self.nodes) <= self.max_nodes:
            return 0
        removed = self._prune_internal()
        if removed:
            self.save()
        return removed

    def _prune_internal(self) -> int:
        if self.max_nodes <= 0 or len(self.nodes) <= self.max_nodes:
            return 0
        protected: set[str] = set()
        cur = self.current
        while cur is not None and cur in self.nodes:
            protected.add(cur)
            cur = self.nodes[cur].parent
        candidates = [
            nid
            for nid, n in self.nodes.items()
            if nid not in protected and n.status == "rolled_back"
        ]
        candidates.sort(
            key=lambda nid: (self.nodes[nid].applied_at, nid)
        )
        excess = len(self.nodes) - self.max_nodes
        removed = 0
        for nid in candidates[:excess]:
            node = self.nodes.pop(nid, None)
            if node is None:
                continue
            removed += 1
            if node.parent and node.parent in self.nodes:
                siblings = self.nodes[node.parent].children
                if nid in siblings:
                    siblings.remove(nid)
            if nid == self.current:
                self.current = node.parent
        return removed
