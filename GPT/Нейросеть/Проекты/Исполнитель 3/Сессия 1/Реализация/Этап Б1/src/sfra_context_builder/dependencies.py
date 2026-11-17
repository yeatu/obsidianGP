"""Required dependency resolution, SCC detection and atomic grouping."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .models import DependencyResolver, RetrievalCandidate, SnapshotRef
from .ranking import rank_key
from .validation import ContractValidationError, parse_candidate


@dataclass(frozen=True)
class DependencyGroup:
    group_id: str
    members: tuple[RetrievalCandidate, ...]
    required: bool
    unresolved_dependency_ids: tuple[str, ...]
    cycles: tuple[tuple[str, ...], ...]
    referenced_ids: frozenset[str]
    parent_context_ids: frozenset[str]

    @property
    def has_unresolved(self) -> bool:
        return bool(self.unresolved_dependency_ids)


def _strongly_connected_components(
    nodes: Sequence[str],
    graph: Mapping[str, set[str]],
) -> list[tuple[str, ...]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in sorted(graph.get(node, ())):
            if target not in indices:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], indices[target])

        if lowlink[node] == indices[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            components.append(tuple(sorted(component)))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return components


def build_dependency_groups(
    candidates: Sequence[RetrievalCandidate],
    *,
    resolver: DependencyResolver | None,
    snapshot: SnapshotRef | None,
    verify_resolved_hash: Callable[[RetrievalCandidate], bool],
    diagnostics: list[dict[str, object]],
) -> tuple[list[DependencyGroup], list[RetrievalCandidate], int]:
    """Resolve missing IDs in the same pinned snapshot and build undirected atomic groups."""
    by_id = {candidate.node_id: candidate for candidate in candidates}
    original_ids = set(by_id)
    references: dict[str, set[str]] = {}
    parent_refs: set[str] = set()
    unresolved_by_owner: dict[str, set[str]] = defaultdict(set)
    rejected_resolved = 0

    for candidate in tuple(by_id.values()):
        deps = set(candidate.required_with)
        if candidate.parent_context_required:
            if candidate.parent_node_id:
                deps.add(candidate.parent_node_id)
                parent_refs.add(candidate.parent_node_id)
            else:
                unresolved_by_owner[candidate.node_id].add("missing_parent_node_id")
        references[candidate.node_id] = deps

    missing_ids = sorted({
        target
        for deps in references.values()
        for target in deps
        if target not in by_id
    })
    if missing_ids and resolver is not None and snapshot is not None:
        for missing_id in missing_ids:
            try:
                raw = resolver.resolve_node(missing_id, snapshot)
            except Exception as exc:  # resolver is an adapter boundary
                raw = None
                diagnostics.append({
                    "code": "dependency_resolver_error",
                    "severity": "warning",
                    "message": f"Не удалось разрешить обязательный узел {missing_id}.",
                    "node_ids": [missing_id],
                    "details": {"error_type": type(exc).__name__},
                })
            if raw is None:
                continue
            try:
                resolved = parse_candidate(
                    raw,
                    original_order=len(candidates) + len(by_id),
                    dependency=True,
                )
            except ContractValidationError as exc:
                rejected_resolved += 1
                diagnostics.append({
                    "code": "dependency_candidate_invalid",
                    "severity": "error",
                    "message": f"Resolver вернул некорректный узел {missing_id}.",
                    "node_ids": [missing_id],
                    "details": {"reason": str(exc)},
                })
                continue
            if resolved.node_id != missing_id or not verify_resolved_hash(resolved):
                rejected_resolved += 1
                diagnostics.append({
                    "code": "dependency_candidate_integrity_error",
                    "severity": "error",
                    "message": f"Resolver вернул неверный ID или Content Hash для {missing_id}.",
                    "node_ids": [missing_id],
                    "details": {"returned_node_id": resolved.node_id},
                })
                continue
            if missing_id not in by_id:
                by_id[missing_id] = resolved

    graph: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    undirected: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    referenced_ids: set[str] = set()
    valid_parent_refs: set[str] = set()

    for owner_id, deps in references.items():
        for target in sorted(deps):
            if target not in by_id:
                unresolved_by_owner[owner_id].add(target)
                continue
            owner = by_id[owner_id]
            dependency = by_id[target]
            if owner.source_path == dependency.source_path:
                mismatch: str | None = None
                if (
                    owner.document_hash is not None
                    and dependency.document_hash is not None
                    and owner.document_hash != dependency.document_hash
                ):
                    mismatch = "document_hash_mismatch"
                elif (
                    owner.index_generation is not None
                    and dependency.index_generation is not None
                    and owner.index_generation != dependency.index_generation
                ):
                    mismatch = "snapshot_generation_mismatch"
                if mismatch:
                    diagnostics.append({
                        "code": mismatch,
                        "severity": "error",
                        "message": (
                            f"Обязательные узлы {owner_id} и {target} относятся к разным "
                            "версиям одного документа."
                        ),
                        "node_ids": [owner_id, target],
                        "details": {"source_path": owner.source_path},
                    })
                    unresolved_by_owner[owner_id].add(target)
            graph[owner_id].add(target)
            undirected[owner_id].add(target)
            undirected[target].add(owner_id)
            referenced_ids.add(target)
            if target in parent_refs:
                valid_parent_refs.add(target)

    components = _strongly_connected_components(list(by_id), graph)
    cycles: list[tuple[str, ...]] = []
    for component in components:
        if len(component) > 1 or (
            len(component) == 1 and component[0] in graph.get(component[0], set())
        ):
            cycles.append(component)
            diagnostics.append({
                "code": "required_dependency_cycle_collapsed",
                "severity": "warning",
                "message": "Циклическая зависимость свёрнута в неделимую группу.",
                "node_ids": list(component),
                "details": {"component": list(component)},
            })

    visited: set[str] = set()
    groups: list[DependencyGroup] = []
    for node_id in sorted(by_id):
        if node_id in visited:
            continue
        stack = [node_id]
        component_ids: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component_ids:
                continue
            component_ids.add(current)
            visited.add(current)
            stack.extend(sorted(undirected[current] - component_ids, reverse=True))

        members = tuple(
            sorted((by_id[item] for item in component_ids), key=rank_key)
        )
        unresolved = sorted({
            dependency_id
            for owner_id in component_ids
            for dependency_id in unresolved_by_owner.get(owner_id, ())
        })
        group_cycles = tuple(
            cycle for cycle in cycles if set(cycle).issubset(component_ids)
        )
        digest = hashlib.sha256("\n".join(sorted(component_ids)).encode("utf-8")).hexdigest()[:12]
        groups.append(DependencyGroup(
            group_id=f"dep_{digest}",
            members=members,
            required=any(member.preservation == "required" for member in members),
            unresolved_dependency_ids=tuple(unresolved),
            cycles=group_cycles,
            referenced_ids=frozenset(component_ids & referenced_ids),
            parent_context_ids=frozenset(component_ids & valid_parent_refs),
        ))

    groups.sort(key=lambda group: min(rank_key(member) for member in group.members))
    return groups, list(by_id.values()), rejected_resolved
