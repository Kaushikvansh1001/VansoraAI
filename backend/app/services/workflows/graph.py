import math
from dataclasses import dataclass, field

from app.core.errors import AppError
from app.services.workflows.catalog import (
    AI_TYPES,
    LOGIC_TYPES,
    MAX_AI_CALLS,
    MAX_EDGES,
    MAX_NODES,
    NODE_TYPES,
    TRIGGERS,
    clean_config,
)


@dataclass
class NodeSpec:
    id: str
    node_type: str
    label: str
    config: dict
    position_x: float = 0
    position_y: float = 0


@dataclass
class EdgeSpec:
    source: str
    target: str
    source_handle: str
    id: str | None = None
    target_handle: str | None = None


@dataclass
class PreparedGraph:
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    order: list[NodeSpec] = field(default_factory=list)


def prepare_graph(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> PreparedGraph:
    if len(nodes) > MAX_NODES:
        raise AppError("invalid_workflow", f"A workflow can contain at most {MAX_NODES} nodes.", 400)
    if len(edges) > MAX_EDGES:
        raise AppError("invalid_workflow", f"A workflow can contain at most {MAX_EDGES} connections.", 400)
    prepared_nodes: list[NodeSpec] = []
    seen: set[str] = set()
    triggers = 0
    ai_nodes = 0
    for node in nodes:
        if node.id in seen:
            raise AppError("invalid_workflow", "Each node needs its own id.", 400)
        seen.add(node.id)
        node_type = (node.node_type or "").strip().lower()
        if node_type not in NODE_TYPES:
            raise AppError("invalid_workflow", "That node type is not available.", 400)
        label = " ".join((node.label or "").split())
        if not label or len(label) > 160:
            raise AppError("invalid_workflow", "Each node needs a name of 160 characters or fewer.", 400)
        if node_type in TRIGGERS:
            triggers += 1
        if node_type in AI_TYPES:
            ai_nodes += 1
        prepared_nodes.append(
            NodeSpec(
                id=node.id,
                node_type=node_type,
                label=label,
                config=clean_config(node_type, label, node.config or {}),
                position_x=_position(node.position_x),
                position_y=_position(node.position_y),
            )
        )
    if triggers != 1:
        raise AppError("invalid_workflow", "A workflow needs exactly one trigger.", 400)
    if ai_nodes > MAX_AI_CALLS:
        raise AppError("invalid_workflow", f"A workflow can use at most {MAX_AI_CALLS} AI nodes.", 400)

    by_id = {node.id: node for node in prepared_nodes}
    prepared_edges: list[EdgeSpec] = []
    seen_edges: set[tuple[str, str, str]] = set()
    incoming = {node.id: 0 for node in prepared_nodes}
    outgoing: dict[str, list[EdgeSpec]] = {node.id: [] for node in prepared_nodes}
    for edge in edges:
        source = by_id.get(edge.source)
        target = by_id.get(edge.target)
        if source is None or target is None:
            raise AppError("invalid_workflow", "Connect nodes that belong to this workflow.", 400)
        if source.id == target.id:
            raise AppError("invalid_workflow", f"{source.label} cannot connect to itself.", 400)
        if target.node_type in TRIGGERS:
            raise AppError("invalid_workflow", "A trigger cannot have an incoming connection.", 400)
        handle = _handle(source, edge.source_handle)
        target_handle = edge.target_handle or None
        if target_handle not in {None, "", "in"}:
            raise AppError("invalid_workflow", f"{target.label}: that input is not available.", 400)
        key = (source.id, target.id, handle)
        if key in seen_edges:
            raise AppError("invalid_workflow", f"{source.label} is already connected to {target.label}.", 400)
        seen_edges.add(key)
        prepared = EdgeSpec(source.id, target.id, handle, edge.id, None)
        prepared_edges.append(prepared)
        outgoing[source.id].append(prepared)
        incoming[target.id] += 1

    roots = [node for node in prepared_nodes if incoming[node.id] == 0]
    if len(roots) != 1 or roots[0].node_type not in TRIGGERS:
        raise AppError("invalid_workflow", "Connect every node to the trigger.", 400)
    order = _order(prepared_nodes, outgoing, incoming, roots[0])
    if len(order) != len(prepared_nodes):
        raise AppError("invalid_workflow", "Connect the nodes without a loop.", 400)
    return PreparedGraph(prepared_nodes, prepared_edges, order)


def _position(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AppError("invalid_workflow", "Node positions must be numbers.", 400) from exc
    if not math.isfinite(number) or number < -4000 or number > 4000:
        raise AppError("invalid_workflow", "Move the node back onto the canvas.", 400)
    return number


def _handle(source: NodeSpec, handle: str | None) -> str:
    cleaned = (handle or "").strip().lower()
    if source.node_type in LOGIC_TYPES:
        if cleaned not in {"true", "false"}:
            raise AppError("invalid_workflow", f"{source.label}: connect the Yes or No output.", 400)
        return cleaned
    if cleaned not in {"", "out"}:
        raise AppError("invalid_workflow", f"{source.label}: that output is not available.", 400)
    return "out"


def _order(nodes: list[NodeSpec], outgoing: dict[str, list[EdgeSpec]], incoming: dict[str, int], root: NodeSpec) -> list[NodeSpec]:
    by_id = {node.id: node for node in nodes}
    pending = dict(incoming)
    ready = [root]
    order: list[NodeSpec] = []
    while ready:
        ready.sort(key=lambda node: (node.position_x, node.position_y, node.label, node.id))
        current = ready.pop(0)
        order.append(current)
        for edge in outgoing[current.id]:
            pending[edge.target] -= 1
            if pending[edge.target] == 0:
                ready.append(by_id[edge.target])
    return order
