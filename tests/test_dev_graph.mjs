import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';

import {
  GraphError,
  canonicalHash,
  completionState,
  finishNode,
  initializeGraph,
  readyNodes,
  renderGraphFile,
  renderGraphSvg,
  startNode,
  validateGraph,
} from '../scripts/dev_graph.mjs';

const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scriptPath = path.join(skillRoot, 'scripts', 'dev_graph.mjs');

function validGraph() {
  return {
    schema_version: 1,
    id: 'example',
    title: 'Example graph',
    spec: '../specs/example.md',
    plan: '../plans/example.md',
    entry: 'build',
    required_gates: ['verify'],
    nodes: [
      {id: 'build', title: 'Build', type: 'action', owner: 'main-agent', inputs: ['approved-plan'], outputs: ['implementation'], pass_condition: 'focused tests pass', required: true},
      {id: 'verify', title: 'Verify', type: 'gate', owner: 'main-agent', inputs: ['implementation'], outputs: ['evidence'], pass_condition: 'fresh verification passes', required: true},
      {id: 'rework', title: 'Rework', type: 'action', owner: 'main-agent', inputs: ['failure'], outputs: ['correction'], pass_condition: 'gate can rerun', required: false},
      {id: 'approval', title: 'Scope approval', type: 'approval', owner: 'user', inputs: ['scope'], outputs: ['approval'], pass_condition: 'user approves', required: false},
      {id: 'success', title: 'Success', type: 'terminal', owner: 'main-agent', inputs: ['gates'], outputs: ['completion'], pass_condition: 'gates passed', outcome: 'success', required: true},
      {id: 'stopped', title: 'Stopped', type: 'terminal', owner: 'main-agent', inputs: ['blocker'], outputs: ['report'], pass_condition: 'reported', outcome: 'stopped', required: false},
    ],
    edges: [
      {from: 'build', to: 'verify', event: 'pass'},
      {from: 'build', to: 'rework', event: 'fail', max_traversals: 2},
      {from: 'build', to: 'approval', event: 'scope_change'},
      {from: 'build', to: 'stopped', event: 'blocked'},
      {from: 'verify', to: 'success', event: 'pass'},
      {from: 'verify', to: 'rework', event: 'fail', max_traversals: 2},
      {from: 'verify', to: 'approval', event: 'scope_change'},
      {from: 'verify', to: 'stopped', event: 'blocked'},
      {from: 'rework', to: 'verify', event: 'pass', max_traversals: 2},
      {from: 'rework', to: 'stopped', event: 'fail'},
      {from: 'rework', to: 'approval', event: 'scope_change'},
      {from: 'rework', to: 'stopped', event: 'blocked'},
      {from: 'approval', to: 'build', event: 'pass', max_traversals: 1},
      {from: 'approval', to: 'stopped', event: 'fail'},
      {from: 'approval', to: 'stopped', event: 'blocked'},
    ],
  };
}

test('accepts a valid graph', () => {
  validateGraph(validGraph());
});

test('rejects an edge that targets a missing node', () => {
  const graph = validGraph();
  graph.edges[0].to = 'missing';
  assert.throws(() => validateGraph(graph), /不存在的节点/);
});

test('rejects max traversals outside the safe integer range', () => {
  const graph = validGraph();
  graph.edges[1].max_traversals = 9_007_199_254_740_992;
  assert.throws(() => validateGraph(graph), /安全整数/);
});

test('rejects an unbounded cycle', () => {
  const graph = validGraph();
  graph.edges.push({from: 'verify', to: 'build', event: 'fail'});
  assert.throws(() => validateGraph(graph), /无上限循环/);
});

test('rejects a gate without a fail edge', () => {
  const graph = validGraph();
  graph.edges = graph.edges.filter(edge => !(edge.from === 'verify' && edge.event === 'fail'));
  assert.throws(() => validateGraph(graph), /失败边/);
});

test('rejects a success path that bypasses a required gate', () => {
  const graph = validGraph();
  graph.edges.push({from: 'build', to: 'success', event: 'pass'});
  assert.throws(() => validateGraph(graph), /绕过必要门禁/);
});

test('canonical hash preserves Unicode and sorts object keys recursively', () => {
  const value = {中文: '换行\n引号"', nested: {z: 1, a: true}};
  assert.equal(canonicalHash(value), '07b67d4d59d614a01dd7bb53b8f7768e18d9bf8d62477a866a2c5174a97d8562');
});

test('renders a safe deterministic SVG with nodes edges and loop limits', () => {
  const graph = validGraph();
  graph.title = '开发图 <预览> & 安全';
  graph.nodes[0].title = '构建 <script>alert(1)</script>';
  const svg = renderGraphSvg(graph);
  assert.match(svg, /^<\?xml[^]*<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.match(svg, /开发图 &lt;预览&gt; &amp; 安全/);
  assert.doesNotMatch(svg, /<script>|javascript:/i);
  for (const node of graph.nodes) assert.match(svg, new RegExp(`data-node-id="${node.id}"`));
  for (const event of new Set(graph.edges.map(edge => edge.event))) assert.match(svg, new RegExp(`>${event}`));
  assert.match(svg, /0\/2/);
});

test('render file defaults to a sibling SVG and CLI honors output', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'dev-graph-node-'));
  const graphPath = path.join(directory, '开发图.json');
  const explicitPath = path.join(directory, 'custom.svg');
  writeFileSync(graphPath, `${JSON.stringify(validGraph(), null, 2)}\n`, 'utf8');
  assert.equal(renderGraphFile(graphPath), path.join(directory, '开发图.svg'));
  execFileSync(process.execPath, [scriptPath, 'render', graphPath, '--output', explicitPath], {encoding: 'utf8'});
  assert.match(readFileSync(explicitPath, 'utf8'), /<svg/);
});

function advanceToRunningVerify(graph) {
  graph = startNode(graph, 'build');
  graph = finishNode(graph, 'build', 'pass', 'RED/GREEN test passed');
  return startNode(graph, 'verify');
}

function graphAtRunningSuccessTerminal() {
  let graph = advanceToRunningVerify(initializeGraph(validGraph()));
  graph = finishNode(graph, 'verify', 'pass', 'verification passed');
  return startNode(graph, 'success');
}

test('initializes only the entry as ready', () => {
  const graph = initializeGraph(validGraph());
  assert.deepEqual(readyNodes(graph), ['build']);
  assert.equal(graph.runtime.statuses.verify, 'pending');
});

test('only ready nodes start and only running nodes finish', () => {
  const graph = initializeGraph(validGraph());
  assert.throws(() => startNode(graph, 'verify'), /不是 ready/);
  assert.throws(() => finishNode(graph, 'build', 'pass', 'evidence'), /不是 running/);
});

test('outcomes require evidence and failures activate rework', () => {
  let graph = advanceToRunningVerify(initializeGraph(validGraph()));
  assert.throws(() => finishNode(graph, 'verify', 'pass', ''), /证据/);
  graph = finishNode(graph, 'verify', 'fail', 'exit 1');
  assert.equal(graph.runtime.statuses.verify, 'failed');
  assert.equal(graph.runtime.statuses.rework, 'ready');
  assert.equal(graph.runtime.statuses.success, 'blocked');
  assert.equal(graph.runtime.history.at(-1).evidence, 'exit 1');
});

test('bounded edges reject a transition after the retry limit', () => {
  let graph = advanceToRunningVerify(initializeGraph(validGraph()));
  for (let attempt = 0; attempt < 2; attempt += 1) {
    graph = finishNode(graph, 'verify', 'fail', `verify failed ${attempt + 1}`);
    graph = startNode(graph, 'rework');
    graph = finishNode(graph, 'rework', 'pass', `rework passed ${attempt + 1}`);
    graph = startNode(graph, 'verify');
  }
  assert.throws(() => finishNode(graph, 'verify', 'fail', 'third failure'), /重试上限/);
});

test('scope changes activate approval and preserve append-only history', () => {
  let graph = startNode(initializeGraph(validGraph()), 'build');
  graph = finishNode(graph, 'build', 'scope_change', 'public API changed');
  assert.equal(graph.runtime.statuses.approval, 'ready');
  assert.equal(graph.runtime.statuses.build, 'skipped');
  assert.equal(graph.runtime.history.length, 2);
  assert.equal(graph.runtime.history[1].prev_hash, graph.runtime.history[0].hash);
});

test('runtime and history tampering is rejected', () => {
  const graph = initializeGraph(validGraph());
  graph.runtime.statuses.build = 'passed';
  assert.throws(() => validateGraph(graph), /运行状态与历史不一致/);
});

test('reinitializing history requires approval evidence', () => {
  const graph = startNode(initializeGraph(validGraph()), 'build');
  assert.throws(() => initializeGraph(graph), /审批证据/);
  const reset = initializeGraph(graph, 'user approved revised graph');
  assert.deepEqual(reset.runtime.history, []);
  assert.equal(reset.runtime.initialization_evidence, 'user approved revised graph');
});

test('completion requires the success terminal and required gate evidence', () => {
  let graph = graphAtRunningSuccessTerminal();
  assert.equal(completionState(graph), 'active');
  graph = finishNode(graph, 'success', 'pass', 'all gates verified');
  assert.equal(completionState(graph), 'complete');
});

test('CLI initializes starts finishes and reports status', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'dev-graph-cli-'));
  const graphPath = path.join(directory, 'graph.json');
  writeFileSync(graphPath, `${JSON.stringify(validGraph(), null, 2)}\n`, 'utf8');
  execFileSync(process.execPath, [scriptPath, 'init', graphPath], {encoding: 'utf8'});
  assert.match(readFileSync(path.join(directory, 'graph.svg'), 'utf8'), /ready/);
  execFileSync(process.execPath, [scriptPath, 'start', graphPath, 'build'], {encoding: 'utf8'});
  execFileSync(process.execPath, [scriptPath, 'pass', graphPath, 'build', '--evidence', 'CLI passed'], {encoding: 'utf8'});
  const status = JSON.parse(execFileSync(process.execPath, [scriptPath, 'status', graphPath], {encoding: 'utf8'}));
  assert.deepEqual(status.ready, ['verify']);
  assert.equal(status.history_entries, 2);
});

export {validGraph};
