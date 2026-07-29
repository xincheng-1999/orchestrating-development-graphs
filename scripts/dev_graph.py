#!/usr/bin/env python3
"""Validate and execute persistent development graphs without running task commands."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class GraphError(ValueError):
    """Raised when a graph definition or transition violates an invariant."""


VALID_NODE_TYPES = {"action", "gate", "approval", "decision", "terminal"}
VALID_EVENTS = {"pass", "fail", "blocked", "scope_change"}
VALID_STATUSES = {
    "pending",
    "ready",
    "running",
    "passed",
    "failed",
    "blocked",
    "skipped",
}
MAX_SAFE_INTEGER = (1 << 53) - 1


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphError(message)


def load_graph(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            graph = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphError(f"无法读取图文件 {path}: {exc}") from exc
    _require(isinstance(graph, dict), "图文件根节点必须是 JSON 对象")
    return graph


def atomic_write(path: Path, graph: dict) -> None:
    payload = json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, payload, "图文件")


def _atomic_write_text(path: Path, payload: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise GraphError(f"无法原子写入{label} {path}: {exc}") from exc


def _node_map(graph: dict) -> dict[str, dict]:
    nodes = graph.get("nodes")
    _require(isinstance(nodes, list) and nodes, "nodes 必须是非空数组")
    result: dict[str, dict] = {}
    for index, node in enumerate(nodes):
        _require(isinstance(node, dict), f"nodes[{index}] 必须是对象")
        node_id = node.get("id")
        _require(isinstance(node_id, str) and node_id, f"nodes[{index}].id 必须是非空字符串")
        _require(node_id not in result, f"节点 ID 重复: {node_id}")
        _require(node.get("type") in VALID_NODE_TYPES, f"节点 {node_id} 类型非法")
        for field in ("title", "owner", "pass_condition"):
            _require(
                isinstance(node.get(field), str) and bool(node[field].strip()),
                f"节点 {node_id}.{field} 必须是非空字符串",
            )
        for field in ("inputs", "outputs"):
            _require(isinstance(node.get(field), list), f"节点 {node_id}.{field} 必须是数组")
        _require(isinstance(node.get("required"), bool), f"节点 {node_id}.required 必须是布尔值")
        if node["type"] == "terminal":
            _require(node.get("outcome") in {"success", "stopped"}, f"终点 {node_id} outcome 非法")
        result[node_id] = node
    return result


def _validated_edges(graph: dict, node_ids: set[str]) -> list[dict]:
    edges = graph.get("edges")
    _require(isinstance(edges, list), "edges 必须是数组")
    validated: list[dict] = []
    for index, edge in enumerate(edges):
        _require(isinstance(edge, dict), f"edges[{index}] 必须是对象")
        source = edge.get("from")
        target = edge.get("to")
        _require(source in node_ids, f"边引用不存在的节点: {source}")
        _require(target in node_ids, f"边引用不存在的节点: {target}")
        _require(edge.get("event") in VALID_EVENTS, f"边 {source}->{target} 使用非法事件")
        if "max_traversals" in edge:
            limit = edge["max_traversals"]
            _require(
                isinstance(limit, int)
                and not isinstance(limit, bool)
                and 0 < limit <= MAX_SAFE_INTEGER,
                f"边 {source}->{target}.max_traversals 必须是正安全整数",
            )
        validated.append(edge)
    return validated


def _adjacency(node_ids: Iterable[str], edges: Iterable[dict]) -> dict[str, list[str]]:
    result = {node_id: [] for node_id in node_ids}
    for edge in edges:
        result[edge["from"]].append(edge["to"])
    return result


def _reachable(entry: str, adjacency: dict[str, list[str]], avoided: str | None = None) -> set[str]:
    if entry == avoided:
        return set()
    seen: set[str] = set()
    stack = [entry]
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id == avoided:
            continue
        seen.add(node_id)
        stack.extend(adjacency[node_id])
    return seen


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(target) for target in adjacency[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in adjacency if node_id not in visited)


def validate_graph(graph: dict) -> None:
    _require(isinstance(graph, dict), "图必须是对象")
    _require(graph.get("schema_version") == 1, "schema_version 必须为 1")
    for field in ("id", "title", "spec", "plan", "entry"):
        _require(
            isinstance(graph.get(field), str) and bool(graph[field].strip()),
            f"{field} 必须是非空字符串",
        )

    nodes = _node_map(graph)
    node_ids = set(nodes)
    entry = graph["entry"]
    _require(entry in node_ids, f"入口引用不存在的节点: {entry}")
    _require(nodes[entry]["type"] != "terminal", "入口不能是终点")

    edges = _validated_edges(graph, node_ids)
    outgoing: dict[str, list[dict]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        outgoing[edge["from"]].append(edge)

    for node_id, node in nodes.items():
        if node["type"] == "terminal":
            _require(not outgoing[node_id], f"终点 {node_id} 不能有出边")
        if node["type"] == "gate":
            _require(
                any(edge["event"] == "fail" for edge in outgoing[node_id]),
                f"门禁 {node_id} 缺少失败边",
            )

    adjacency = _adjacency(node_ids, edges)
    reachable = _reachable(entry, adjacency)
    unreachable_required = sorted(
        node_id for node_id, node in nodes.items() if node["required"] and node_id not in reachable
    )
    _require(
        not unreachable_required,
        f"必要节点不可达: {', '.join(unreachable_required)}",
    )

    success_terminals = {
        node_id
        for node_id, node in nodes.items()
        if node["type"] == "terminal" and node.get("outcome") == "success"
    }
    _require(success_terminals, "至少需要一个 success 终点")
    _require(bool(success_terminals & reachable), "success 终点不可达")

    unbounded_edges = [edge for edge in edges if "max_traversals" not in edge]
    if _has_cycle(_adjacency(node_ids, unbounded_edges)):
        raise GraphError("图包含无上限循环；为回退边设置 max_traversals")

    required_gates = graph.get("required_gates")
    _require(isinstance(required_gates, list), "required_gates 必须是数组")
    _require(len(required_gates) == len(set(required_gates)), "required_gates 不能重复")
    for gate_id in required_gates:
        _require(gate_id in nodes, f"必要门禁不存在: {gate_id}")
        _require(nodes[gate_id]["type"] == "gate", f"必要门禁 {gate_id} 不是 gate 节点")
        path_without_gate = _reachable(entry, adjacency, avoided=gate_id)
        if success_terminals & path_without_gate:
            raise GraphError(f"存在绕过必要门禁 {gate_id} 的成功路径")

    if "runtime" in graph:
        _validate_runtime(graph, nodes, edges)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _definition_hash(graph: dict) -> str:
    definition = {key: value for key, value in graph.items() if key != "runtime"}
    return _canonical_hash(definition)


def _initial_statuses(nodes: dict[str, dict], entry: str) -> dict[str, str]:
    return {
        node_id: "ready" if node_id == entry else "pending"
        for node_id in nodes
    }


def _edge_key(index: int, edge: dict) -> str:
    return f"{index}:{edge['from']}:{edge['event']}:{edge['to']}"


def _preview_layout(graph: dict) -> tuple[dict[str, tuple[int, int]], int, int]:
    nodes = _node_map(graph)
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in graph["edges"]:
        outgoing[edge["from"]].append(edge["to"])

    depths = {graph["entry"]: 0}
    queue = [graph["entry"]]
    for node_id in queue:
        for target in outgoing[node_id]:
            if target not in depths:
                depths[target] = depths[node_id] + 1
                queue.append(target)
    fallback_depth = max(depths.values(), default=0) + 1
    for node_id in nodes:
        depths.setdefault(node_id, fallback_depth)

    columns: dict[int, list[str]] = {}
    for node in graph["nodes"]:
        columns.setdefault(depths[node["id"]], []).append(node["id"])

    margin_x, margin_y = 70, 130
    node_width, node_height = 280, 104
    gap_x, gap_y = 170, 74
    positions: dict[str, tuple[int, int]] = {}
    for depth in sorted(columns):
        for row, node_id in enumerate(columns[depth]):
            positions[node_id] = (
                margin_x + depth * (node_width + gap_x),
                margin_y + row * (node_height + gap_y),
            )
    width = margin_x * 2 + (max(columns, default=0) + 1) * node_width + max(columns, default=0) * gap_x
    max_rows = max((len(column) for column in columns.values()), default=1)
    height = margin_y + max_rows * node_height + max(0, max_rows - 1) * gap_y + 100
    return positions, width, height


def _preview_text(value: object, limit: int = 42) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) > limit:
        normalized = normalized[: limit - 1] + "…"
    return html.escape(normalized, quote=True)


def render_graph_svg(graph: dict) -> str:
    """Render a validated graph as a deterministic, dependency-free SVG preview."""
    validate_graph(graph)
    positions, width, height = _preview_layout(graph)
    node_width, node_height = 280, 104
    runtime = graph.get("runtime") if isinstance(graph.get("runtime"), dict) else {}
    statuses = runtime.get("statuses", {}) if isinstance(runtime, dict) else {}
    traversals = runtime.get("edge_traversals", {}) if isinstance(runtime, dict) else {}
    fills = {
        "uninitialized": "#f8fafc",
        "pending": "#f1f5f9",
        "ready": "#dbeafe",
        "running": "#fef3c7",
        "passed": "#dcfce7",
        "failed": "#fee2e2",
        "blocked": "#e5e7eb",
        "skipped": "#ede9fe",
    }
    event_colors = {
        "pass": "#15803d",
        "fail": "#dc2626",
        "blocked": "#64748b",
        "scope_change": "#7c3aed",
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "  <defs>",
        '    <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto" markerUnits="strokeWidth">',
        '      <path d="M0,0 L10,3.5 L0,7 Z" fill="context-stroke"/>',
        "    </marker>",
        "  </defs>",
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        f'  <text x="40" y="48" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700" fill="#0f172a">{_preview_text(graph["title"], 80)}</text>',
        f'  <text x="40" y="78" font-family="Consolas, monospace" font-size="13" fill="#475569">{_preview_text(graph["id"], 100)}</text>',
        '  <g id="edges" fill="none">',
    ]

    for index, edge in enumerate(graph["edges"]):
        source_x, source_y = positions[edge["from"]]
        target_x, target_y = positions[edge["to"]]
        color = event_colors[edge["event"]]
        if edge["from"] == edge["to"]:
            x = source_x + node_width
            y = source_y + node_height / 2
            path_data = f"M {x} {y} C {x + 90} {y - 70}, {x + 90} {y + 70}, {x} {y + 20}"
            label_x, label_y = x + 76, y - 46
        elif target_x > source_x:
            start_x, start_y = source_x + node_width, source_y + node_height / 2
            end_x, end_y = target_x, target_y + node_height / 2
            control = max(50, (end_x - start_x) / 2)
            path_data = f"M {start_x} {start_y} C {start_x + control} {start_y}, {end_x - control} {end_y}, {end_x} {end_y}"
            label_x, label_y = (start_x + end_x) / 2, (start_y + end_y) / 2 - 8
        else:
            start_x, start_y = source_x, source_y + node_height / 2
            end_x, end_y = target_x + node_width, target_y + node_height / 2
            bend_y = max(start_y, end_y) + 72 + (index % 3) * 18
            path_data = f"M {start_x} {start_y} C {start_x - 55} {bend_y}, {end_x + 55} {bend_y}, {end_x} {end_y}"
            label_x, label_y = (start_x + end_x) / 2, bend_y - 8
        edge_key = _edge_key(index, edge)
        label = edge["event"]
        if "max_traversals" in edge:
            label += f" {traversals.get(edge_key, 0)}/{edge['max_traversals']}"
        lines.extend(
            [
                f'    <path data-edge-index="{index}" d="{path_data}" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"/>',
                f'    <text x="{label_x}" y="{label_y}" text-anchor="middle" font-family="Consolas, monospace" font-size="12" fill="{color}">{_preview_text(label, 60)}</text>',
            ]
        )
    lines.extend(["  </g>", '  <g id="nodes">'])

    for node in graph["nodes"]:
        node_id = node["id"]
        x, y = positions[node_id]
        status = statuses.get(node_id, "uninitialized")
        stroke = "#16a34a" if node.get("outcome") == "success" else "#334155"
        if node.get("outcome") == "stopped":
            stroke = "#b91c1c"
        lines.extend(
            [
                f'    <g data-node-id="{_preview_text(node_id, 200)}">',
                f'      <rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="14" fill="{fills[status]}" stroke="{stroke}" stroke-width="2"/>',
                f'      <text x="{x + 16}" y="{y + 28}" font-family="Segoe UI, sans-serif" font-size="16" font-weight="700" fill="#0f172a">{_preview_text(node["title"])}</text>',
                f'      <text x="{x + 16}" y="{y + 53}" font-family="Consolas, monospace" font-size="12" fill="#475569">{_preview_text(node_id, 44)}</text>',
                f'      <text x="{x + 16}" y="{y + 78}" font-family="Segoe UI, sans-serif" font-size="12" fill="#334155">{_preview_text(node["type"], 24)} · {_preview_text(status, 24)}</text>',
                "    </g>",
            ]
        )
    lines.extend(["  </g>", "</svg>", ""])
    return "\n".join(lines)


def render_graph_file(graph_path: Path, output_path: Path | None = None) -> Path:
    output = output_path or graph_path.with_suffix(".svg")
    svg = render_graph_svg(load_graph(graph_path))
    _atomic_write_text(output, svg, "预览文件")
    return output


def _persist_graph_and_preview(graph_path: Path, graph: dict) -> None:
    svg = render_graph_svg(graph)
    atomic_write(graph_path, graph)
    _atomic_write_text(graph_path.with_suffix(".svg"), svg, "预览文件")


def _validate_status_snapshot(statuses: object, node_ids: set[str], label: str) -> None:
    _require(isinstance(statuses, dict), f"{label} 必须是对象")
    _require(set(statuses) == node_ids, f"{label} 必须完整覆盖所有节点")
    for node_id, status in statuses.items():
        _require(status in VALID_STATUSES, f"{label}.{node_id} 状态非法: {status}")


def _validate_traversal_snapshot(traversals: object, allowed_keys: set[str], label: str) -> None:
    _require(isinstance(traversals, dict), f"{label} 必须是对象")
    for key, count in traversals.items():
        _require(key in allowed_keys, f"{label} 包含未知边: {key}")
        _require(
            isinstance(count, int) and not isinstance(count, bool) and count >= 0,
            f"{label}.{key} 必须是非负整数",
        )


def _validate_runtime(graph: dict, nodes: dict[str, dict], edges: list[dict]) -> None:
    runtime = graph.get("runtime")
    _require(isinstance(runtime, dict), "runtime 必须是对象")
    _require(
        isinstance(runtime.get("initialization_evidence", ""), str),
        "runtime.initialization_evidence 必须是字符串",
    )
    _require(
        runtime.get("definition_hash") == _definition_hash(graph),
        "图定义已变更；审批并重新 init 后才能继续",
    )

    node_ids = set(nodes)
    statuses = runtime.get("statuses")
    traversals = runtime.get("edge_traversals")
    history = runtime.get("history")
    allowed_edge_keys = {_edge_key(index, edge) for index, edge in enumerate(edges)}
    _validate_status_snapshot(statuses, node_ids, "runtime.statuses")
    _validate_traversal_snapshot(traversals, allowed_edge_keys, "runtime.edge_traversals")
    _require(isinstance(history, list), "runtime.history 必须是数组")

    expected_statuses = _initial_statuses(nodes, graph["entry"])
    expected_traversals: dict[str, int] = {}
    previous_hash = ""
    for index, record in enumerate(history):
        _require(isinstance(record, dict), f"history[{index}] 必须是对象")
        _require(record.get("seq") == index + 1, f"history[{index}] seq 不连续")
        _require(record.get("node") in node_ids, f"history[{index}] 节点不存在")
        _require(
            record.get("event") in VALID_EVENTS | {"start"},
            f"history[{index}] 事件非法",
        )
        _require(
            isinstance(record.get("timestamp"), str) and bool(record["timestamp"]),
            f"history[{index}] 缺少时间戳",
        )
        _require(record.get("prev_hash") == previous_hash, f"history[{index}] 哈希链断裂")
        stored_hash = record.get("hash")
        record_without_hash = {key: value for key, value in record.items() if key != "hash"}
        _require(stored_hash == _canonical_hash(record_without_hash), f"history[{index}] 哈希无效")
        _require(
            record.get("statuses_before") == expected_statuses,
            f"history[{index}] 前置状态与历史不一致",
        )
        _require(
            record.get("edge_traversals_before") == expected_traversals,
            f"history[{index}] 前置边次数与历史不一致",
        )
        _validate_status_snapshot(record.get("statuses_after"), node_ids, f"history[{index}].statuses_after")
        _validate_traversal_snapshot(
            record.get("edge_traversals_after"),
            allowed_edge_keys,
            f"history[{index}].edge_traversals_after",
        )
        expected_statuses = record["statuses_after"]
        expected_traversals = record["edge_traversals_after"]
        previous_hash = stored_hash

    _require(statuses == expected_statuses, "运行状态与历史不一致")
    _require(traversals == expected_traversals, "边次数与历史不一致")


def initialize_graph(definition: dict, approval_evidence: str = "") -> dict:
    graph = copy.deepcopy(definition)
    existing_runtime = graph.get("runtime")
    existing_history = existing_runtime.get("history", []) if isinstance(existing_runtime, dict) else []
    if existing_history and not approval_evidence.strip():
        raise GraphError("重新初始化已有历史必须提供审批证据")
    graph.pop("runtime", None)
    validate_graph(graph)
    nodes = _node_map(graph)
    graph["runtime"] = {
        "definition_hash": _definition_hash(graph),
        "initialization_evidence": approval_evidence.strip(),
        "statuses": _initial_statuses(nodes, graph["entry"]),
        "edge_traversals": {},
        "history": [],
    }
    validate_graph(graph)
    return graph


def ready_nodes(graph: dict) -> list[str]:
    validate_graph(graph)
    statuses = graph["runtime"]["statuses"]
    return [node["id"] for node in graph["nodes"] if statuses[node["id"]] == "ready"]


def _append_history(
    graph: dict,
    *,
    node_id: str,
    event: str,
    evidence: str,
    output: str,
    activated: list[str],
    statuses_before: dict[str, str],
    traversals_before: dict[str, int],
) -> None:
    history = graph["runtime"]["history"]
    record = {
        "seq": len(history) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node_id,
        "event": event,
        "evidence": evidence,
        "output": output,
        "activated": activated,
        "statuses_before": statuses_before,
        "statuses_after": copy.deepcopy(graph["runtime"]["statuses"]),
        "edge_traversals_before": traversals_before,
        "edge_traversals_after": copy.deepcopy(graph["runtime"]["edge_traversals"]),
        "prev_hash": history[-1]["hash"] if history else "",
    }
    record["hash"] = _canonical_hash(record)
    history.append(record)


def start_node(graph: dict, node_id: str) -> dict:
    validate_graph(graph)
    result = copy.deepcopy(graph)
    statuses = result["runtime"]["statuses"]
    _require(node_id in statuses, f"节点不存在: {node_id}")
    _require(statuses[node_id] == "ready", f"节点 {node_id} 不是 ready")
    statuses_before = copy.deepcopy(statuses)
    traversals_before = copy.deepcopy(result["runtime"]["edge_traversals"])
    statuses[node_id] = "running"
    _append_history(
        result,
        node_id=node_id,
        event="start",
        evidence="",
        output="",
        activated=[],
        statuses_before=statuses_before,
        traversals_before=traversals_before,
    )
    validate_graph(result)
    return result


def finish_node(
    graph: dict,
    node_id: str,
    event: str,
    evidence: str,
    output: str = "",
) -> dict:
    validate_graph(graph)
    _require(event in VALID_EVENTS, f"非法事件: {event}")
    _require(isinstance(evidence, str) and bool(evidence.strip()), "状态迁移必须提供证据")
    result = copy.deepcopy(graph)
    nodes = _node_map(result)
    statuses = result["runtime"]["statuses"]
    _require(node_id in nodes, f"节点不存在: {node_id}")
    _require(statuses[node_id] == "running", f"节点 {node_id} 不是 running")

    node = nodes[node_id]
    if node["type"] == "terminal":
        _require(event == "pass", f"终点 {node_id} 只接受 pass")
        selected_edges: list[tuple[int, dict]] = []
    else:
        selected_edges = [
            (index, edge)
            for index, edge in enumerate(result["edges"])
            if edge["from"] == node_id and edge["event"] == event
        ]
        _require(selected_edges, f"节点 {node_id} 没有 {event} 边")

    traversals = result["runtime"]["edge_traversals"]
    for index, edge in selected_edges:
        if "max_traversals" in edge:
            key = _edge_key(index, edge)
            if traversals.get(key, 0) >= edge["max_traversals"]:
                raise GraphError(f"边 {edge['from']}->{edge['to']} 已达到重试上限")

    statuses_before = copy.deepcopy(statuses)
    traversals_before = copy.deepcopy(traversals)
    statuses[node_id] = {
        "pass": "passed",
        "fail": "failed",
        "blocked": "blocked",
        "scope_change": "skipped",
    }[event]

    selected_targets = {edge["to"] for _, edge in selected_edges}
    for edge in result["edges"]:
        if edge["from"] != node_id or edge["event"] == event:
            continue
        target = edge["to"]
        if target not in selected_targets and statuses[target] in {"pending", "ready", "blocked"}:
            statuses[target] = "blocked"

    activated = []
    for index, edge in selected_edges:
        key = _edge_key(index, edge)
        traversals[key] = traversals.get(key, 0) + 1
        target = edge["to"]
        statuses[target] = "ready"
        if target not in activated:
            activated.append(target)

    _append_history(
        result,
        node_id=node_id,
        event=event,
        evidence=evidence.strip(),
        output=output,
        activated=activated,
        statuses_before=statuses_before,
        traversals_before=traversals_before,
    )
    validate_graph(result)
    return result


def completion_state(graph: dict) -> str:
    validate_graph(graph)
    nodes = _node_map(graph)
    statuses = graph["runtime"]["statuses"]
    history = graph["runtime"]["history"]
    passed_success = any(
        node["type"] == "terminal"
        and node.get("outcome") == "success"
        and statuses[node_id] == "passed"
        for node_id, node in nodes.items()
    )
    if passed_success:
        for gate_id in graph["required_gates"]:
            gate_has_evidence = any(
                record["node"] == gate_id
                and record["event"] == "pass"
                and bool(record["evidence"].strip())
                for record in history
            )
            if statuses[gate_id] != "passed" or not gate_has_evidence:
                return "active"
        return "complete"
    passed_stopped = any(
        node["type"] == "terminal"
        and node.get("outcome") == "stopped"
        and statuses[node_id] == "passed"
        for node_id, node in nodes.items()
    )
    return "stopped" if passed_stopped else "active"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化或重新初始化开发图")
    init_parser.add_argument("definition", type=Path)
    init_parser.add_argument("--output", type=Path)
    init_parser.add_argument("--approval-evidence", default="")

    validate_parser = subparsers.add_parser("validate", help="校验开发图")
    validate_parser.add_argument("graph", type=Path)

    ready_parser = subparsers.add_parser("ready", help="列出 ready 节点")
    ready_parser.add_argument("graph", type=Path)

    start_parser = subparsers.add_parser("start", help="启动 ready 节点")
    start_parser.add_argument("graph", type=Path)
    start_parser.add_argument("node")

    for command in ("pass", "fail", "block", "scope-change"):
        outcome_parser = subparsers.add_parser(command, help=f"记录 {command} 结果")
        outcome_parser.add_argument("graph", type=Path)
        outcome_parser.add_argument("node")
        outcome_parser.add_argument("--evidence", required=True)
        outcome_parser.add_argument("--output", default="")

    status_parser = subparsers.add_parser("status", help="显示图执行状态")
    status_parser.add_argument("graph", type=Path)

    render_parser = subparsers.add_parser("render", help="生成 SVG 图形预览")
    render_parser.add_argument("graph", type=Path)
    render_parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            definition = load_graph(args.definition)
            graph = initialize_graph(definition, approval_evidence=args.approval_evidence)
            output = args.output or args.definition
            _persist_graph_and_preview(output, graph)
            print(f"INITIALIZED: {output}")
            return 0
        if args.command == "validate":
            graph = load_graph(args.graph)
            validate_graph(graph)
            print(f"VALID: {args.graph}")
            return 0
        if args.command == "ready":
            graph = load_graph(args.graph)
            for node_id in ready_nodes(graph):
                print(node_id)
            return 0
        if args.command == "start":
            graph = start_node(load_graph(args.graph), args.node)
            _persist_graph_and_preview(args.graph, graph)
            print(f"RUNNING: {args.node}")
            return 0
        if args.command in {"pass", "fail", "block", "scope-change"}:
            event = {
                "pass": "pass",
                "fail": "fail",
                "block": "blocked",
                "scope-change": "scope_change",
            }[args.command]
            graph = finish_node(
                load_graph(args.graph),
                args.node,
                event,
                args.evidence,
                args.output,
            )
            _persist_graph_and_preview(args.graph, graph)
            print(f"{event.upper()}: {args.node}")
            return 0
        if args.command == "status":
            graph = load_graph(args.graph)
            validate_graph(graph)
            print(
                json.dumps(
                    {
                        "graph": graph["id"],
                        "completion": completion_state(graph),
                        "ready": ready_nodes(graph),
                        "statuses": graph["runtime"]["statuses"],
                        "history_entries": len(graph["runtime"]["history"]),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "render":
            output = render_graph_file(args.graph, args.output)
            print(f"RENDERED: {output}")
            return 0
    except GraphError as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    raise AssertionError(f"未处理的命令: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
