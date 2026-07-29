#!/usr/bin/env node
/** Validate, preview, and execute persistent development graphs without running task commands. */

import {createHash, randomBytes} from 'node:crypto';
import {
  closeSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export class GraphError extends Error {
  constructor(message) {
    super(message);
    this.name = 'GraphError';
  }
}

const VALID_NODE_TYPES = new Set(['action', 'gate', 'approval', 'decision', 'terminal']);
const VALID_EVENTS = new Set(['pass', 'fail', 'blocked', 'scope_change']);
const VALID_STATUSES = new Set(['pending', 'ready', 'running', 'passed', 'failed', 'blocked', 'skipped']);

function requireGraph(condition, message) {
  if (!condition) throw new GraphError(message);
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function canonicalValue(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    requireGraph(Number.isSafeInteger(value), `${location} 必须是安全整数`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => canonicalValue(item, `${location}[${index}]`));
  requireGraph(isPlainObject(value), `${location} 包含非 JSON 值`);
  const result = {};
  for (const key of Object.keys(value).sort()) result[key] = canonicalValue(value[key], `${location}.${key}`);
  return result;
}

export function canonicalHash(value) {
  const payload = JSON.stringify(canonicalValue(value));
  return createHash('sha256').update(payload, 'utf8').digest('hex');
}

export function loadGraph(graphPath) {
  try {
    const graph = JSON.parse(readFileSync(graphPath, 'utf8'));
    requireGraph(isPlainObject(graph), '图文件根节点必须是 JSON 对象');
    return graph;
  } catch (error) {
    if (error instanceof GraphError) throw error;
    throw new GraphError(`无法读取图文件 ${graphPath}: ${error.message}`);
  }
}

function atomicWriteText(outputPath, payload, label) {
  const directory = path.dirname(outputPath);
  mkdirSync(directory, {recursive: true});
  const temporaryPath = path.join(
    directory,
    `.${path.basename(outputPath)}.${process.pid}.${randomBytes(8).toString('hex')}.tmp`,
  );
  let descriptor;
  try {
    descriptor = openSync(temporaryPath, 'wx');
    writeFileSync(descriptor, payload, 'utf8');
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    renameSync(temporaryPath, outputPath);
  } catch (error) {
    if (descriptor !== undefined) {
      try { closeSync(descriptor); } catch {}
    }
    try { unlinkSync(temporaryPath); } catch {}
    throw new GraphError(`无法原子写入${label} ${outputPath}: ${error.message}`);
  }
}

export function atomicWrite(outputPath, graph) {
  atomicWriteText(outputPath, `${JSON.stringify(graph, null, 2)}\n`, '图文件');
}

function nodeMap(graph) {
  requireGraph(Array.isArray(graph.nodes) && graph.nodes.length > 0, 'nodes 必须是非空数组');
  const result = new Map();
  graph.nodes.forEach((node, index) => {
    requireGraph(isPlainObject(node), `nodes[${index}] 必须是对象`);
    requireGraph(typeof node.id === 'string' && node.id.length > 0, `nodes[${index}].id 必须是非空字符串`);
    requireGraph(!result.has(node.id), `节点 ID 重复: ${node.id}`);
    requireGraph(VALID_NODE_TYPES.has(node.type), `节点 ${node.id} 类型非法`);
    for (const field of ['title', 'owner', 'pass_condition']) {
      requireGraph(typeof node[field] === 'string' && node[field].trim(), `节点 ${node.id}.${field} 必须是非空字符串`);
    }
    for (const field of ['inputs', 'outputs']) requireGraph(Array.isArray(node[field]), `节点 ${node.id}.${field} 必须是数组`);
    requireGraph(typeof node.required === 'boolean', `节点 ${node.id}.required 必须是布尔值`);
    if (node.type === 'terminal') requireGraph(['success', 'stopped'].includes(node.outcome), `终点 ${node.id} outcome 非法`);
    result.set(node.id, node);
  });
  return result;
}

function validatedEdges(graph, nodeIds) {
  requireGraph(Array.isArray(graph.edges), 'edges 必须是数组');
  return graph.edges.map((edge, index) => {
    requireGraph(isPlainObject(edge), `edges[${index}] 必须是对象`);
    requireGraph(nodeIds.has(edge.from), `边引用不存在的节点: ${edge.from}`);
    requireGraph(nodeIds.has(edge.to), `边引用不存在的节点: ${edge.to}`);
    requireGraph(VALID_EVENTS.has(edge.event), `边 ${edge.from}->${edge.to} 使用非法事件`);
    if (Object.hasOwn(edge, 'max_traversals')) {
      requireGraph(Number.isSafeInteger(edge.max_traversals) && edge.max_traversals > 0, `边 ${edge.from}->${edge.to}.max_traversals 必须是正安全整数`);
    }
    return edge;
  });
}

function adjacency(nodeIds, edges) {
  const result = new Map([...nodeIds].map(nodeId => [nodeId, []]));
  for (const edge of edges) result.get(edge.from).push(edge.to);
  return result;
}

function reachable(entry, graphAdjacency, avoided = null) {
  if (entry === avoided) return new Set();
  const seen = new Set();
  const stack = [entry];
  while (stack.length > 0) {
    const nodeId = stack.pop();
    if (seen.has(nodeId) || nodeId === avoided) continue;
    seen.add(nodeId);
    stack.push(...graphAdjacency.get(nodeId));
  }
  return seen;
}

function hasCycle(graphAdjacency) {
  const visiting = new Set();
  const visited = new Set();
  function visit(nodeId) {
    if (visiting.has(nodeId)) return true;
    if (visited.has(nodeId)) return false;
    visiting.add(nodeId);
    if (graphAdjacency.get(nodeId).some(visit)) return true;
    visiting.delete(nodeId);
    visited.add(nodeId);
    return false;
  }
  return [...graphAdjacency.keys()].some(nodeId => !visited.has(nodeId) && visit(nodeId));
}

export function validateGraph(graph) {
  requireGraph(isPlainObject(graph), '图必须是对象');
  requireGraph(graph.schema_version === 1, 'schema_version 必须为 1');
  for (const field of ['id', 'title', 'spec', 'plan', 'entry']) {
    requireGraph(typeof graph[field] === 'string' && graph[field].trim(), `${field} 必须是非空字符串`);
  }
  const nodes = nodeMap(graph);
  const nodeIds = new Set(nodes.keys());
  requireGraph(nodeIds.has(graph.entry), `入口引用不存在的节点: ${graph.entry}`);
  requireGraph(nodes.get(graph.entry).type !== 'terminal', '入口不能是终点');
  const edges = validatedEdges(graph, nodeIds);
  const outgoing = new Map([...nodeIds].map(nodeId => [nodeId, []]));
  for (const edge of edges) outgoing.get(edge.from).push(edge);
  for (const [nodeId, node] of nodes) {
    if (node.type === 'terminal') requireGraph(outgoing.get(nodeId).length === 0, `终点 ${nodeId} 不能有出边`);
    if (node.type === 'gate') requireGraph(outgoing.get(nodeId).some(edge => edge.event === 'fail'), `门禁 ${nodeId} 缺少失败边`);
  }
  const allAdjacency = adjacency(nodeIds, edges);
  const allReachable = reachable(graph.entry, allAdjacency);
  const unreachableRequired = [...nodes].filter(([nodeId, node]) => node.required && !allReachable.has(nodeId)).map(([nodeId]) => nodeId).sort();
  requireGraph(unreachableRequired.length === 0, `必要节点不可达: ${unreachableRequired.join(', ')}`);
  const successTerminals = new Set([...nodes].filter(([, node]) => node.type === 'terminal' && node.outcome === 'success').map(([nodeId]) => nodeId));
  requireGraph(successTerminals.size > 0, '至少需要一个 success 终点');
  requireGraph([...successTerminals].some(nodeId => allReachable.has(nodeId)), 'success 终点不可达');
  const unboundedEdges = edges.filter(edge => !Object.hasOwn(edge, 'max_traversals'));
  requireGraph(!hasCycle(adjacency(nodeIds, unboundedEdges)), '图包含无上限循环；为回退边设置 max_traversals');
  requireGraph(Array.isArray(graph.required_gates), 'required_gates 必须是数组');
  requireGraph(new Set(graph.required_gates).size === graph.required_gates.length, 'required_gates 不能重复');
  for (const gateId of graph.required_gates) {
    requireGraph(nodes.has(gateId), `必要门禁不存在: ${gateId}`);
    requireGraph(nodes.get(gateId).type === 'gate', `必要门禁 ${gateId} 不是 gate 节点`);
    const withoutGate = reachable(graph.entry, allAdjacency, gateId);
    if ([...successTerminals].some(nodeId => withoutGate.has(nodeId))) throw new GraphError(`存在绕过必要门禁 ${gateId} 的成功路径`);
  }
  if (Object.hasOwn(graph, 'runtime')) validateRuntime(graph, nodes, edges);
}

function edgeKey(index, edge) {
  return `${index}:${edge.from}:${edge.event}:${edge.to}`;
}

function deepClone(value) {
  return structuredClone(value);
}

function deepEqual(left, right) {
  return JSON.stringify(canonicalValue(left)) === JSON.stringify(canonicalValue(right));
}

function definitionHash(graph) {
  const definition = Object.fromEntries(Object.entries(graph).filter(([key]) => key !== 'runtime'));
  return canonicalHash(definition);
}

function initialStatuses(nodes, entry) {
  return Object.fromEntries([...nodes.keys()].map(nodeId => [nodeId, nodeId === entry ? 'ready' : 'pending']));
}

function validateStatusSnapshot(statuses, nodeIds, label) {
  requireGraph(isPlainObject(statuses), `${label} 必须是对象`);
  requireGraph(deepEqual(Object.keys(statuses).sort(), [...nodeIds].sort()), `${label} 必须完整覆盖所有节点`);
  for (const [nodeId, status] of Object.entries(statuses)) requireGraph(VALID_STATUSES.has(status), `${label}.${nodeId} 状态非法: ${status}`);
}

function validateTraversalSnapshot(traversals, allowedKeys, label) {
  requireGraph(isPlainObject(traversals), `${label} 必须是对象`);
  for (const [key, count] of Object.entries(traversals)) {
    requireGraph(allowedKeys.has(key), `${label} 包含未知边: ${key}`);
    requireGraph(Number.isSafeInteger(count) && count >= 0, `${label}.${key} 必须是非负整数`);
  }
}

function validateRuntime(graph, nodes, edges) {
  const runtime = graph.runtime;
  requireGraph(isPlainObject(runtime), 'runtime 必须是对象');
  requireGraph(typeof (runtime.initialization_evidence ?? '') === 'string', 'runtime.initialization_evidence 必须是字符串');
  requireGraph(runtime.definition_hash === definitionHash(graph), '图定义已变更；审批并重新 init 后才能继续');
  const nodeIds = new Set(nodes.keys());
  const allowedEdgeKeys = new Set(edges.map((edge, index) => edgeKey(index, edge)));
  validateStatusSnapshot(runtime.statuses, nodeIds, 'runtime.statuses');
  validateTraversalSnapshot(runtime.edge_traversals, allowedEdgeKeys, 'runtime.edge_traversals');
  requireGraph(Array.isArray(runtime.history), 'runtime.history 必须是数组');

  let expectedStatuses = initialStatuses(nodes, graph.entry);
  let expectedTraversals = {};
  let previousHash = '';
  runtime.history.forEach((record, index) => {
    requireGraph(isPlainObject(record), `history[${index}] 必须是对象`);
    requireGraph(record.seq === index + 1, `history[${index}] seq 不连续`);
    requireGraph(nodeIds.has(record.node), `history[${index}] 节点不存在`);
    requireGraph(new Set([...VALID_EVENTS, 'start']).has(record.event), `history[${index}] 事件非法`);
    requireGraph(typeof record.timestamp === 'string' && record.timestamp.length > 0, `history[${index}] 缺少时间戳`);
    requireGraph(record.prev_hash === previousHash, `history[${index}] 哈希链断裂`);
    const {hash: storedHash, ...withoutHash} = record;
    requireGraph(storedHash === canonicalHash(withoutHash), `history[${index}] 哈希无效`);
    requireGraph(deepEqual(record.statuses_before, expectedStatuses), `history[${index}] 前置状态与历史不一致`);
    requireGraph(deepEqual(record.edge_traversals_before, expectedTraversals), `history[${index}] 前置边次数与历史不一致`);
    validateStatusSnapshot(record.statuses_after, nodeIds, `history[${index}].statuses_after`);
    validateTraversalSnapshot(record.edge_traversals_after, allowedEdgeKeys, `history[${index}].edge_traversals_after`);
    expectedStatuses = record.statuses_after;
    expectedTraversals = record.edge_traversals_after;
    previousHash = storedHash;
  });
  requireGraph(deepEqual(runtime.statuses, expectedStatuses), '运行状态与历史不一致');
  requireGraph(deepEqual(runtime.edge_traversals, expectedTraversals), '边次数与历史不一致');
}

export function initializeGraph(definition, approvalEvidence = '') {
  const graph = deepClone(definition);
  const existingHistory = isPlainObject(graph.runtime) && Array.isArray(graph.runtime.history) ? graph.runtime.history : [];
  if (existingHistory.length > 0 && !approvalEvidence.trim()) throw new GraphError('重新初始化已有历史必须提供审批证据');
  delete graph.runtime;
  validateGraph(graph);
  const nodes = nodeMap(graph);
  graph.runtime = {
    definition_hash: definitionHash(graph),
    initialization_evidence: approvalEvidence.trim(),
    statuses: initialStatuses(nodes, graph.entry),
    edge_traversals: {},
    history: [],
  };
  validateGraph(graph);
  return graph;
}

export function readyNodes(graph) {
  validateGraph(graph);
  return graph.nodes.filter(node => graph.runtime.statuses[node.id] === 'ready').map(node => node.id);
}

function appendHistory(graph, {nodeId, event, evidence, output, activated, statusesBefore, traversalsBefore}) {
  const history = graph.runtime.history;
  const record = {
    seq: history.length + 1,
    timestamp: new Date().toISOString(),
    node: nodeId,
    event,
    evidence,
    output,
    activated,
    statuses_before: statusesBefore,
    statuses_after: deepClone(graph.runtime.statuses),
    edge_traversals_before: traversalsBefore,
    edge_traversals_after: deepClone(graph.runtime.edge_traversals),
    prev_hash: history.length > 0 ? history.at(-1).hash : '',
  };
  record.hash = canonicalHash(record);
  history.push(record);
}

export function startNode(graph, nodeId) {
  validateGraph(graph);
  const result = deepClone(graph);
  const statuses = result.runtime.statuses;
  requireGraph(Object.hasOwn(statuses, nodeId), `节点不存在: ${nodeId}`);
  requireGraph(statuses[nodeId] === 'ready', `节点 ${nodeId} 不是 ready`);
  const statusesBefore = deepClone(statuses);
  const traversalsBefore = deepClone(result.runtime.edge_traversals);
  statuses[nodeId] = 'running';
  appendHistory(result, {nodeId, event: 'start', evidence: '', output: '', activated: [], statusesBefore, traversalsBefore});
  validateGraph(result);
  return result;
}

export function finishNode(graph, nodeId, event, evidence, output = '') {
  validateGraph(graph);
  requireGraph(VALID_EVENTS.has(event), `非法事件: ${event}`);
  requireGraph(typeof evidence === 'string' && evidence.trim(), '状态迁移必须提供证据');
  const result = deepClone(graph);
  const nodes = nodeMap(result);
  const statuses = result.runtime.statuses;
  requireGraph(nodes.has(nodeId), `节点不存在: ${nodeId}`);
  requireGraph(statuses[nodeId] === 'running', `节点 ${nodeId} 不是 running`);
  let selectedEdges;
  if (nodes.get(nodeId).type === 'terminal') {
    requireGraph(event === 'pass', `终点 ${nodeId} 只接受 pass`);
    selectedEdges = [];
  } else {
    selectedEdges = result.edges.map((edge, index) => [index, edge]).filter(([, edge]) => edge.from === nodeId && edge.event === event);
    requireGraph(selectedEdges.length > 0, `节点 ${nodeId} 没有 ${event} 边`);
  }
  const traversals = result.runtime.edge_traversals;
  for (const [index, edge] of selectedEdges) {
    if (Object.hasOwn(edge, 'max_traversals')) requireGraph((traversals[edgeKey(index, edge)] ?? 0) < edge.max_traversals, `边 ${edge.from}->${edge.to} 已达到重试上限`);
  }
  const statusesBefore = deepClone(statuses);
  const traversalsBefore = deepClone(traversals);
  statuses[nodeId] = {pass: 'passed', fail: 'failed', blocked: 'blocked', scope_change: 'skipped'}[event];
  const selectedTargets = new Set(selectedEdges.map(([, edge]) => edge.to));
  for (const edge of result.edges) {
    if (edge.from === nodeId && edge.event !== event && !selectedTargets.has(edge.to) && ['pending', 'ready', 'blocked'].includes(statuses[edge.to])) statuses[edge.to] = 'blocked';
  }
  const activated = [];
  for (const [index, edge] of selectedEdges) {
    const key = edgeKey(index, edge);
    traversals[key] = (traversals[key] ?? 0) + 1;
    statuses[edge.to] = 'ready';
    if (!activated.includes(edge.to)) activated.push(edge.to);
  }
  appendHistory(result, {nodeId, event, evidence: evidence.trim(), output, activated, statusesBefore, traversalsBefore});
  validateGraph(result);
  return result;
}

export function completionState(graph) {
  validateGraph(graph);
  const nodes = nodeMap(graph);
  const statuses = graph.runtime.statuses;
  const history = graph.runtime.history;
  const passedSuccess = [...nodes].some(([nodeId, node]) => node.type === 'terminal' && node.outcome === 'success' && statuses[nodeId] === 'passed');
  if (passedSuccess) {
    for (const gateId of graph.required_gates) {
      const hasEvidence = history.some(record => record.node === gateId && record.event === 'pass' && typeof record.evidence === 'string' && record.evidence.trim());
      if (statuses[gateId] !== 'passed' || !hasEvidence) return 'active';
    }
    return 'complete';
  }
  const passedStopped = [...nodes].some(([nodeId, node]) => node.type === 'terminal' && node.outcome === 'stopped' && statuses[nodeId] === 'passed');
  return passedStopped ? 'stopped' : 'active';
}

function previewLayout(graph) {
  const nodes = nodeMap(graph);
  const outgoing = new Map([...nodes.keys()].map(nodeId => [nodeId, []]));
  for (const edge of graph.edges) outgoing.get(edge.from).push(edge.to);
  const depths = new Map([[graph.entry, 0]]);
  const queue = [graph.entry];
  for (let index = 0; index < queue.length; index += 1) {
    const nodeId = queue[index];
    for (const target of outgoing.get(nodeId)) {
      if (!depths.has(target)) {
        depths.set(target, depths.get(nodeId) + 1);
        queue.push(target);
      }
    }
  }
  const fallbackDepth = Math.max(...depths.values(), 0) + 1;
  for (const nodeId of nodes.keys()) if (!depths.has(nodeId)) depths.set(nodeId, fallbackDepth);
  const columns = new Map();
  for (const node of graph.nodes) {
    const depth = depths.get(node.id);
    if (!columns.has(depth)) columns.set(depth, []);
    columns.get(depth).push(node.id);
  }
  const marginX = 70;
  const marginY = 130;
  const nodeWidth = 280;
  const nodeHeight = 104;
  const gapX = 170;
  const gapY = 74;
  const positions = new Map();
  for (const depth of [...columns.keys()].sort((left, right) => left - right)) {
    columns.get(depth).forEach((nodeId, row) => positions.set(nodeId, [marginX + depth * (nodeWidth + gapX), marginY + row * (nodeHeight + gapY)]));
  }
  const maxDepth = Math.max(...columns.keys(), 0);
  const maxRows = Math.max(...[...columns.values()].map(column => column.length), 1);
  return {
    positions,
    width: marginX * 2 + (maxDepth + 1) * nodeWidth + maxDepth * gapX,
    height: marginY + maxRows * nodeHeight + Math.max(0, maxRows - 1) * gapY + 100,
  };
}

function escapeXml(value, limit = 42) {
  let normalized = String(value).trim().split(/\s+/u).join(' ');
  if (normalized.length > limit) normalized = `${normalized.slice(0, limit - 1)}…`;
  return normalized
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#x27;');
}

export function renderGraphSvg(graph) {
  validateGraph(graph);
  const {positions, width, height} = previewLayout(graph);
  const nodeWidth = 280;
  const nodeHeight = 104;
  const runtime = isPlainObject(graph.runtime) ? graph.runtime : {};
  const statuses = isPlainObject(runtime.statuses) ? runtime.statuses : {};
  const traversals = isPlainObject(runtime.edge_traversals) ? runtime.edge_traversals : {};
  const fills = {uninitialized: '#f8fafc', pending: '#f1f5f9', ready: '#dbeafe', running: '#fef3c7', passed: '#dcfce7', failed: '#fee2e2', blocked: '#e5e7eb', skipped: '#ede9fe'};
  const eventColors = {pass: '#15803d', fail: '#dc2626', blocked: '#64748b', scope_change: '#7c3aed'};
  const lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    '  <defs>',
    '    <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto" markerUnits="strokeWidth">',
    '      <path d="M0,0 L10,3.5 L0,7 Z" fill="context-stroke"/>',
    '    </marker>',
    '  </defs>',
    '  <rect width="100%" height="100%" fill="#ffffff"/>',
    `  <text x="40" y="48" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700" fill="#0f172a">${escapeXml(graph.title, 80)}</text>`,
    `  <text x="40" y="78" font-family="Consolas, monospace" font-size="13" fill="#475569">${escapeXml(graph.id, 100)}</text>`,
    '  <g id="edges" fill="none">',
  ];
  graph.edges.forEach((edge, index) => {
    const [sourceX, sourceY] = positions.get(edge.from);
    const [targetX, targetY] = positions.get(edge.to);
    let pathData;
    let labelX;
    let labelY;
    if (edge.from === edge.to) {
      const x = sourceX + nodeWidth;
      const y = sourceY + nodeHeight / 2;
      pathData = `M ${x} ${y} C ${x + 90} ${y - 70}, ${x + 90} ${y + 70}, ${x} ${y + 20}`;
      labelX = x + 76;
      labelY = y - 46;
    } else if (targetX > sourceX) {
      const startX = sourceX + nodeWidth;
      const startY = sourceY + nodeHeight / 2;
      const endX = targetX;
      const endY = targetY + nodeHeight / 2;
      const control = Math.max(50, (endX - startX) / 2);
      pathData = `M ${startX} ${startY} C ${startX + control} ${startY}, ${endX - control} ${endY}, ${endX} ${endY}`;
      labelX = (startX + endX) / 2;
      labelY = (startY + endY) / 2 - 8;
    } else {
      const startX = sourceX;
      const startY = sourceY + nodeHeight / 2;
      const endX = targetX + nodeWidth;
      const endY = targetY + nodeHeight / 2;
      const bendY = Math.max(startY, endY) + 72 + (index % 3) * 18;
      pathData = `M ${startX} ${startY} C ${startX - 55} ${bendY}, ${endX + 55} ${bendY}, ${endX} ${endY}`;
      labelX = (startX + endX) / 2;
      labelY = bendY - 8;
    }
    let label = edge.event;
    if (Object.hasOwn(edge, 'max_traversals')) label += ` ${traversals[edgeKey(index, edge)] ?? 0}/${edge.max_traversals}`;
    const color = eventColors[edge.event];
    lines.push(`    <path data-edge-index="${index}" d="${pathData}" stroke="${color}" stroke-width="2" marker-end="url(#arrow)"/>`);
    lines.push(`    <text x="${labelX}" y="${labelY}" text-anchor="middle" font-family="Consolas, monospace" font-size="12" fill="${color}">${escapeXml(label, 60)}</text>`);
  });
  lines.push('  </g>', '  <g id="nodes">');
  for (const node of graph.nodes) {
    const [x, y] = positions.get(node.id);
    const status = statuses[node.id] ?? 'uninitialized';
    let stroke = '#334155';
    if (node.outcome === 'success') stroke = '#16a34a';
    if (node.outcome === 'stopped') stroke = '#b91c1c';
    lines.push(`    <g data-node-id="${escapeXml(node.id, 200)}">`);
    lines.push(`      <rect x="${x}" y="${y}" width="${nodeWidth}" height="${nodeHeight}" rx="14" fill="${fills[status] ?? fills.uninitialized}" stroke="${stroke}" stroke-width="2"/>`);
    lines.push(`      <text x="${x + 16}" y="${y + 28}" font-family="Segoe UI, sans-serif" font-size="16" font-weight="700" fill="#0f172a">${escapeXml(node.title)}</text>`);
    lines.push(`      <text x="${x + 16}" y="${y + 53}" font-family="Consolas, monospace" font-size="12" fill="#475569">${escapeXml(node.id, 44)}</text>`);
    lines.push(`      <text x="${x + 16}" y="${y + 78}" font-family="Segoe UI, sans-serif" font-size="12" fill="#334155">${escapeXml(node.type, 24)} · ${escapeXml(status, 24)}</text>`);
    lines.push('    </g>');
  }
  lines.push('  </g>', '</svg>', '');
  return lines.join('\n');
}

export function renderGraphFile(graphPath, outputPath = null) {
  const output = outputPath ?? path.join(path.dirname(graphPath), `${path.basename(graphPath, path.extname(graphPath))}.svg`);
  atomicWriteText(output, renderGraphSvg(loadGraph(graphPath)), '预览文件');
  return output;
}

function parseCommand(argv) {
  const [command, ...tokens] = argv;
  requireGraph(command, '缺少命令');
  const positionals = [];
  const options = {};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token.startsWith('--')) {
      requireGraph(index + 1 < tokens.length && !tokens[index + 1].startsWith('--'), `参数 ${token} 缺少值`);
      requireGraph(!Object.hasOwn(options, token), `参数 ${token} 重复`);
      options[token] = tokens[index + 1];
      index += 1;
    } else {
      positionals.push(token);
    }
  }
  const allowedOptions = {
    init: new Set(['--output', '--approval-evidence']),
    validate: new Set(),
    ready: new Set(),
    start: new Set(),
    pass: new Set(['--evidence', '--output']),
    fail: new Set(['--evidence', '--output']),
    block: new Set(['--evidence', '--output']),
    'scope-change': new Set(['--evidence', '--output']),
    status: new Set(),
    render: new Set(['--output']),
  };
  requireGraph(Object.hasOwn(allowedOptions, command), `未知命令: ${command}`);
  for (const option of Object.keys(options)) requireGraph(allowedOptions[command].has(option), `命令 ${command} 不支持参数 ${option}`);
  const expectedPositionals = new Set(['start', 'pass', 'fail', 'block', 'scope-change']).has(command) ? 2 : 1;
  requireGraph(positionals.length === expectedPositionals, `命令 ${command} 需要 ${expectedPositionals} 个位置参数`);
  if (new Set(['pass', 'fail', 'block', 'scope-change']).has(command)) requireGraph(typeof options['--evidence'] === 'string' && options['--evidence'].trim(), '状态迁移必须提供 --evidence');
  return {command, positionals, options};
}

function persistGraphAndPreview(graphPath, graph) {
  const previewPath = path.join(path.dirname(graphPath), `${path.basename(graphPath, path.extname(graphPath))}.svg`);
  const svg = renderGraphSvg(graph);
  atomicWrite(graphPath, graph);
  atomicWriteText(previewPath, svg, '预览文件');
}

export function main(argv = process.argv.slice(2)) {
  try {
    const {command, positionals, options} = parseCommand(argv);
    const graphPath = positionals[0];
    if (command === 'init') {
      const graph = initializeGraph(loadGraph(graphPath), options['--approval-evidence'] ?? '');
      const output = options['--output'] ?? graphPath;
      persistGraphAndPreview(output, graph);
      process.stdout.write(`INITIALIZED: ${output}\n`);
      return 0;
    }
    if (command === 'validate') {
      validateGraph(loadGraph(graphPath));
      process.stdout.write(`VALID: ${graphPath}\n`);
      return 0;
    }
    if (command === 'ready') {
      for (const nodeId of readyNodes(loadGraph(graphPath))) process.stdout.write(`${nodeId}\n`);
      return 0;
    }
    if (command === 'start') {
      const graph = startNode(loadGraph(graphPath), positionals[1]);
      persistGraphAndPreview(graphPath, graph);
      process.stdout.write(`RUNNING: ${positionals[1]}\n`);
      return 0;
    }
    const outcomeEvents = {pass: 'pass', fail: 'fail', block: 'blocked', 'scope-change': 'scope_change'};
    if (Object.hasOwn(outcomeEvents, command)) {
      const graph = finishNode(
        loadGraph(graphPath),
        positionals[1],
        outcomeEvents[command],
        options['--evidence'],
        options['--output'] ?? '',
      );
      persistGraphAndPreview(graphPath, graph);
      process.stdout.write(`${outcomeEvents[command].toUpperCase()}: ${positionals[1]}\n`);
      return 0;
    }
    if (command === 'status') {
      const graph = loadGraph(graphPath);
      validateGraph(graph);
      process.stdout.write(`${JSON.stringify({
        graph: graph.id,
        completion: completionState(graph),
        ready: readyNodes(graph),
        statuses: graph.runtime.statuses,
        history_entries: graph.runtime.history.length,
      }, null, 2)}\n`);
      return 0;
    }
    if (command === 'render') {
      const rendered = renderGraphFile(graphPath, options['--output'] ?? null);
      process.stdout.write(`RENDERED: ${rendered}\n`);
      return 0;
    }
    throw new GraphError(`未知命令: ${command}`);
  } catch (error) {
    if (error instanceof GraphError) {
      process.stderr.write(`ERROR: ${error.message}\n`);
      return 2;
    }
    throw error;
  }
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (invokedPath && invokedPath === path.resolve(fileURLToPath(import.meta.url))) process.exitCode = main();
