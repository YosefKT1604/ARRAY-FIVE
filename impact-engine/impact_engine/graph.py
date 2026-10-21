"""Directed dependency graph and path enumeration (pure Python, no extra libs)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from .models import DataIssue, DependencyType, EntityType, IssueCode, IssueSeverity
from .validation import BusinessContext


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    dependency_type: DependencyType
    required_quantity: Optional[int] = None
    required_by: Optional[date] = None
    dependency_id: Optional[str] = None
    derived: bool = False


class DependencyGraph:
    def __init__(self) -> None:
        self.node_types: dict[str, EntityType] = {}
        self._out: dict[str, list[Edge]] = {}
        self._in: dict[str, list[Edge]] = {}

    def add_node(self, node_id: str, node_type: EntityType) -> None:
        self.node_types[node_id] = node_type
        self._out.setdefault(node_id, [])
        self._in.setdefault(node_id, [])

    def add_edge(self, edge: Edge) -> None:
        self._out[edge.source].append(edge)
        self._in[edge.target].append(edge)

    def out_edges(self, node_id: str) -> list[Edge]:
        return self._out.get(node_id, [])

    def in_edges(self, node_id: str) -> list[Edge]:
        return self._in.get(node_id, [])

    def has_edge(self, source: str, target: str, dependency_type: DependencyType) -> bool:
        return any(e.target == target and e.dependency_type is dependency_type for e in self.out_edges(source))

    def all_paths(
        self,
        start: str,
        edge_filter: Optional[Callable[[Edge], bool]] = None,
        max_paths_per_node: int = 20,
    ) -> tuple[dict[str, list[list[str]]], set[str], list[tuple[str, str]]]:
        """Enumerate simple (cycle-free) paths from `start` to every reachable node.

        Returns (paths_by_node, nodes_whose_paths_were_capped, cycle_edges_seen).
        A node reached by several routes appears ONCE with all routes listed --
        that is how duplicates collapse while every dependency path is preserved.
        """
        paths: dict[str, list[list[str]]] = {}
        truncated: set[str] = set()
        cycles: list[tuple[str, str]] = []
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            for edge in self.out_edges(node):
                if edge_filter is not None and not edge_filter(edge):
                    continue
                nxt = edge.target
                if nxt in path:
                    if (node, nxt) not in cycles:
                        cycles.append((node, nxt))
                    continue
                bucket = paths.setdefault(nxt, [])
                if len(bucket) >= max_paths_per_node:
                    truncated.add(nxt)
                    continue
                new_path = path + [nxt]
                bucket.append(new_path)
                stack.append((nxt, new_path))
        for bucket in paths.values():
            bucket.sort(key=lambda p: (len(p), p))  # deterministic, shortest first
        return paths, truncated, cycles


def build_graph(ctx: BusinessContext) -> DependencyGraph:
    graph = DependencyGraph()
    for registry, kind in ((ctx.suppliers, EntityType.SUPPLIER), (ctx.resources, EntityType.RESOURCE),
                           (ctx.deliveries, EntityType.DELIVERY), (ctx.jobs, EntityType.JOB),
                           (ctx.commitments, EntityType.COMMITMENT)):
        for node_id in registry:
            graph.add_node(node_id, kind)
    for d in ctx.dependencies:
        graph.add_edge(Edge(d.source_id, d.target_id, d.dependency_type, d.required_quantity,
                            d.required_by, d.id))

    # The delivery and commitment records already state these links. If the
    # dependency table forgot them, add them (and say so) rather than miss an impact.
    def derive(source: str, target: str, dep_type: DependencyType, why: str) -> None:
        if not graph.has_edge(source, target, dep_type):
            graph.add_edge(Edge(source, target, dep_type, derived=True))
            ctx.issues.append(DataIssue(code=IssueCode.DERIVED_EDGE, severity=IssueSeverity.INFO,
                                        message=f"No '{dep_type.value}' dependency {source} -> {target}; derived from {why}.",
                                        entity_id=target))

    for dl in ctx.deliveries.values():
        derive(dl.supplier_id, dl.id, DependencyType.SHIPS, f"delivery {dl.id}")
        derive(dl.id, dl.resource_id, DependencyType.SUPPLIES, f"delivery {dl.id}")
    for c in ctx.commitments.values():
        derive(c.job_id, c.id, DependencyType.FULFILS, f"commitment {c.id}")
    return graph
