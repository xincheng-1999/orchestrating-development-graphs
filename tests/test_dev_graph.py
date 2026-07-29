import copy
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "dev_graph.py"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
REFERENCE_PATH = SKILL_ROOT / "references" / "graph-schema.md"
NODE_SCRIPT_PATH = SKILL_ROOT / "scripts" / "dev_graph.mjs"
EXAMPLE_GRAPH_PATH = SKILL_ROOT / "examples" / "development-graph.json"
NODE_EXE = shutil.which("node")

spec = importlib.util.spec_from_file_location("dev_graph", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT_PATH}")
dev_graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_graph)

GraphError = dev_graph.GraphError
validate_graph = dev_graph.validate_graph
initialize_graph = dev_graph.initialize_graph
ready_nodes = dev_graph.ready_nodes
start_node = dev_graph.start_node
finish_node = dev_graph.finish_node
completion_state = dev_graph.completion_state
render_graph_svg = dev_graph.render_graph_svg
render_graph_file = dev_graph.render_graph_file


def valid_graph():
    return {
        "schema_version": 1,
        "id": "example",
        "title": "Example graph",
        "spec": "../specs/example.md",
        "plan": "../plans/example.md",
        "entry": "build",
        "required_gates": ["verify"],
        "nodes": [
            {
                "id": "build",
                "title": "Build",
                "type": "action",
                "owner": "main-agent",
                "inputs": ["approved-plan"],
                "outputs": ["implementation"],
                "pass_condition": "focused tests pass",
                "required": True,
            },
            {
                "id": "verify",
                "title": "Verify",
                "type": "gate",
                "owner": "main-agent",
                "inputs": ["implementation"],
                "outputs": ["verification evidence"],
                "pass_condition": "fresh verification passes",
                "required": True,
            },
            {
                "id": "rework",
                "title": "Rework",
                "type": "action",
                "owner": "main-agent",
                "inputs": ["failure evidence"],
                "outputs": ["minimal correction"],
                "pass_condition": "original gate can be rerun",
                "required": False,
            },
            {
                "id": "approval",
                "title": "Scope approval",
                "type": "approval",
                "owner": "user",
                "inputs": ["scope change"],
                "outputs": ["approval evidence"],
                "pass_condition": "user approves revised artifacts",
                "required": False,
            },
            {
                "id": "success",
                "title": "Success",
                "type": "terminal",
                "owner": "main-agent",
                "inputs": ["required gates"],
                "outputs": ["completion"],
                "pass_condition": "required gates passed",
                "outcome": "success",
                "required": True,
            },
            {
                "id": "stopped",
                "title": "Stopped",
                "type": "terminal",
                "owner": "main-agent",
                "inputs": ["blocker"],
                "outputs": ["blocked report"],
                "pass_condition": "blocker reported",
                "outcome": "stopped",
                "required": False,
            },
        ],
        "edges": [
            {"from": "build", "to": "verify", "event": "pass"},
            {"from": "build", "to": "rework", "event": "fail", "max_traversals": 2},
            {"from": "build", "to": "approval", "event": "scope_change"},
            {"from": "build", "to": "stopped", "event": "blocked"},
            {"from": "verify", "to": "success", "event": "pass"},
            {"from": "verify", "to": "rework", "event": "fail", "max_traversals": 2},
            {"from": "verify", "to": "approval", "event": "scope_change"},
            {"from": "verify", "to": "stopped", "event": "blocked"},
            {"from": "rework", "to": "verify", "event": "pass", "max_traversals": 2},
            {"from": "rework", "to": "stopped", "event": "fail"},
            {"from": "rework", "to": "approval", "event": "scope_change"},
            {"from": "rework", "to": "stopped", "event": "blocked"},
            {"from": "approval", "to": "build", "event": "pass", "max_traversals": 1},
            {"from": "approval", "to": "stopped", "event": "fail"},
            {"from": "approval", "to": "stopped", "event": "blocked"},
        ],
    }


def advance_to_running_verify(graph):
    graph = start_node(graph, "build")
    graph = finish_node(graph, "build", "pass", "RED/GREEN test passed")
    return start_node(graph, "verify")


def graph_with_retry_edge_already_used_twice():
    graph = advance_to_running_verify(initialize_graph(valid_graph()))
    for attempt in range(2):
        graph = finish_node(graph, "verify", "fail", f"verify failed {attempt + 1}")
        graph = start_node(graph, "rework")
        graph = finish_node(graph, "rework", "pass", f"rework passed {attempt + 1}")
        graph = start_node(graph, "verify")
    return graph


def graph_at_running_success_terminal():
    graph = advance_to_running_verify(initialize_graph(valid_graph()))
    graph = finish_node(graph, "verify", "pass", "verification passed")
    return start_node(graph, "success")


def extract_json_example(text, marker):
    anchor = f"<!-- {marker} -->"
    if anchor not in text:
        raise AssertionError(f"缺少示例标记: {anchor}")
    remainder = text.split(anchor, 1)[1]
    opening = "```json\n"
    if opening not in remainder:
        raise AssertionError("示例标记后缺少 JSON 代码块")
    payload = remainder.split(opening, 1)[1].split("```", 1)[0]
    return json.loads(payload)


class GraphValidationTests(unittest.TestCase):
    def test_accepts_valid_graph(self):
        validate_graph(valid_graph())

    def test_distribution_example_validates(self):
        example = json.loads(EXAMPLE_GRAPH_PATH.read_text(encoding="utf-8"))
        validate_graph(example)

    def test_rejects_missing_edge_target(self):
        graph = valid_graph()
        graph["edges"][0]["to"] = "missing"
        with self.assertRaisesRegex(GraphError, "不存在的节点"):
            validate_graph(graph)

    def test_rejects_invalid_event(self):
        graph = valid_graph()
        graph["edges"][0]["event"] = "maybe"
        with self.assertRaisesRegex(GraphError, "非法事件"):
            validate_graph(graph)

    def test_rejects_max_traversals_outside_safe_integer_range(self):
        graph = valid_graph()
        graph["edges"][1]["max_traversals"] = 9_007_199_254_740_992
        with self.assertRaisesRegex(GraphError, "安全整数"):
            validate_graph(graph)

    def test_rejects_unbounded_cycle(self):
        graph = valid_graph()
        graph["edges"].append({"from": "verify", "to": "build", "event": "fail"})
        with self.assertRaisesRegex(GraphError, "无上限循环"):
            validate_graph(graph)

    def test_rejects_gate_without_failure_edge(self):
        graph = valid_graph()
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if not (edge["from"] == "verify" and edge["event"] == "fail")
        ]
        with self.assertRaisesRegex(GraphError, "失败边"):
            validate_graph(graph)

    def test_rejects_success_path_bypassing_required_gate(self):
        graph = valid_graph()
        graph["edges"].append({"from": "build", "to": "success", "event": "pass"})
        with self.assertRaisesRegex(GraphError, "绕过必要门禁"):
            validate_graph(graph)

    def test_rejects_unreachable_required_node(self):
        graph = valid_graph()
        graph["nodes"].append(
            {
                "id": "orphan",
                "title": "Orphan",
                "type": "action",
                "owner": "main-agent",
                "inputs": [],
                "outputs": [],
                "pass_condition": "never",
                "required": True,
            }
        )
        with self.assertRaisesRegex(GraphError, "必要节点不可达"):
            validate_graph(graph)


class GraphRuntimeTests(unittest.TestCase):
    def test_initializes_only_entry_as_ready(self):
        graph = initialize_graph(valid_graph())
        self.assertEqual(ready_nodes(graph), ["build"])
        self.assertEqual(graph["runtime"]["statuses"]["verify"], "pending")

    def test_only_ready_node_can_start(self):
        graph = initialize_graph(valid_graph())
        with self.assertRaisesRegex(GraphError, "不是 ready"):
            start_node(graph, "verify")

    def test_only_running_node_can_finish(self):
        graph = initialize_graph(valid_graph())
        with self.assertRaisesRegex(GraphError, "不是 running"):
            finish_node(graph, "build", "pass", "unit tests")

    def test_gate_pass_requires_evidence(self):
        graph = advance_to_running_verify(initialize_graph(valid_graph()))
        with self.assertRaisesRegex(GraphError, "证据"):
            finish_node(graph, "verify", "pass", "")

    def test_failure_activates_failure_target_and_preserves_history(self):
        graph = advance_to_running_verify(initialize_graph(valid_graph()))
        graph = finish_node(graph, "verify", "fail", "exit 1")
        self.assertEqual(graph["runtime"]["statuses"]["verify"], "failed")
        self.assertEqual(graph["runtime"]["statuses"]["rework"], "ready")
        self.assertEqual(graph["runtime"]["statuses"]["success"], "blocked")
        self.assertEqual(graph["runtime"]["history"][-1]["evidence"], "exit 1")

    def test_retry_limit_stops_additional_transition(self):
        graph = graph_with_retry_edge_already_used_twice()
        with self.assertRaisesRegex(GraphError, "重试上限"):
            finish_node(graph, "verify", "fail", "verify failed a third time")

    def test_scope_change_activates_approval_node(self):
        graph = initialize_graph(valid_graph())
        graph = start_node(graph, "build")
        graph = finish_node(graph, "build", "scope_change", "public API changed")
        self.assertEqual(graph["runtime"]["statuses"]["approval"], "ready")
        self.assertEqual(graph["runtime"]["statuses"]["build"], "skipped")

    def test_success_requires_success_terminal_and_required_gate_evidence(self):
        graph = graph_at_running_success_terminal()
        graph = finish_node(graph, "success", "pass", "all gates verified")
        self.assertEqual(completion_state(graph), "complete")

    def test_success_is_not_complete_before_terminal_passes(self):
        graph = graph_at_running_success_terminal()
        self.assertEqual(completion_state(graph), "active")

    def test_tampered_runtime_or_history_is_rejected(self):
        graph = initialize_graph(valid_graph())
        graph["runtime"]["statuses"]["build"] = "passed"
        with self.assertRaisesRegex(GraphError, "运行状态与历史不一致"):
            validate_graph(graph)

    def test_definition_change_requires_reinitialization(self):
        graph = initialize_graph(valid_graph())
        graph["title"] = "Changed without approval"
        with self.assertRaisesRegex(GraphError, "图定义已变更"):
            validate_graph(graph)

    def test_reinitializing_history_requires_approval_evidence(self):
        graph = start_node(initialize_graph(valid_graph()), "build")
        with self.assertRaisesRegex(GraphError, "重新初始化.*审批证据"):
            initialize_graph(graph)
        reset = initialize_graph(graph, approval_evidence="user approved revised graph")
        self.assertEqual(reset["runtime"]["history"], [])
        self.assertEqual(
            reset["runtime"]["initialization_evidence"],
            "user approved revised graph",
        )

    def test_runtime_created_before_initialization_evidence_remains_valid(self):
        graph = start_node(initialize_graph(valid_graph()), "build")
        del graph["runtime"]["initialization_evidence"]
        validate_graph(graph)

    def test_atomic_round_trip(self):
        graph = initialize_graph(valid_graph())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            dev_graph.atomic_write(path, graph)
            self.assertEqual(dev_graph.load_graph(path), graph)


class GraphPreviewTests(unittest.TestCase):
    def test_renders_uninitialized_graph_as_safe_svg(self):
        graph = valid_graph()
        graph["title"] = "开发图 <预览> & 安全"
        graph["nodes"][0]["title"] = "构建 <script>alert(1)</script>"

        svg = render_graph_svg(graph)

        root = ET.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("开发图 &lt;预览&gt; &amp; 安全", svg)
        self.assertNotIn("<script>", svg)
        self.assertNotIn("javascript:", svg.lower())
        for node in graph["nodes"]:
            self.assertIn(f'data-node-id="{node["id"]}"', svg)
        for event in {edge["event"] for edge in graph["edges"]}:
            self.assertIn(f">{event}", svg)

    def test_renders_runtime_statuses_and_traversal_counts(self):
        initialized = initialize_graph(valid_graph())
        graph = start_node(initialized, "build")

        initial_svg = render_graph_svg(initialized)
        svg = render_graph_svg(graph)

        ET.fromstring(svg)
        self.assertIn("ready", initial_svg)
        self.assertIn("running", svg)
        self.assertIn("0/2", svg)

    def test_render_file_defaults_to_same_name_svg_and_honors_output(self):
        with tempfile.TemporaryDirectory() as directory:
            graph_path = Path(directory) / "开发图.json"
            custom_path = Path(directory) / "preview" / "custom.svg"
            dev_graph.atomic_write(graph_path, valid_graph())

            default_output = render_graph_file(graph_path)
            explicit_output = render_graph_file(graph_path, custom_path)

            self.assertEqual(default_output, graph_path.with_suffix(".svg"))
            self.assertTrue(default_output.is_file())
            self.assertEqual(explicit_output, custom_path)
            self.assertTrue(custom_path.is_file())
            ET.parse(default_output)
            ET.parse(custom_path)

    def test_python_mutating_cli_keeps_default_preview_in_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            graph_path = Path(directory) / "graph.json"
            dev_graph.atomic_write(graph_path, valid_graph())

            subprocess.run(
                [str(shutil.which("python") or "python"), str(SCRIPT_PATH), "init", str(graph_path)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            preview_path = graph_path.with_suffix(".svg")
            self.assertIn("ready", preview_path.read_text(encoding="utf-8"))

            subprocess.run(
                [str(shutil.which("python") or "python"), str(SCRIPT_PATH), "start", str(graph_path), "build"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertIn("running", preview_path.read_text(encoding="utf-8"))


class SkillContractTests(unittest.TestCase):
    def test_skill_requires_executor_only_for_complex(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Complex", text)
        self.assertIn("scripts/dev_graph.py", text)
        self.assertIn("scripts/dev_graph.mjs", text)
        self.assertIn("references/graph-schema.md", text)

    def test_skill_selects_python_then_node_and_blocks_without_either(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Python 3.10+", text)
        self.assertIn("Node.js 18+", text)
        self.assertIn("both runtimes are unavailable", text)
        self.assertIn("Do not probe runtimes for Simple or Standard tasks", text)

    def test_skill_requires_validate_and_render_after_graph_writes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("validate -> render", text)
        self.assertIn("same-name SVG", text)
        reference = REFERENCE_PATH.read_text(encoding="utf-8")
        self.assertIn("dev_graph.py render", reference)
        self.assertIn("dev_graph.mjs render", reference)

    def test_skill_does_not_require_graph_for_simple_or_standard(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Simple tasks must not create a graph artifact", text)
        self.assertIn("Standard tasks must not create a graph artifact", text)

    def test_reference_example_validates(self):
        example = extract_json_example(
            REFERENCE_PATH.read_text(encoding="utf-8"),
            marker="minimal-complex-graph",
        )
        validate_graph(example)


@unittest.skipUnless(NODE_EXE, "需要 Node.js 运行互操作测试")
class CrossRuntimeInteropTests(unittest.TestCase):
    def run_node(self, *arguments):
        return subprocess.run(
            [NODE_EXE, str(NODE_SCRIPT_PATH), *map(str, arguments)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_python_history_can_continue_in_node(self):
        with tempfile.TemporaryDirectory() as directory:
            graph_path = Path(directory) / "graph.json"
            graph = start_node(initialize_graph(valid_graph()), "build")
            dev_graph.atomic_write(graph_path, graph)

            self.run_node("pass", graph_path, "build", "--evidence", "node accepted python history")

            continued = dev_graph.load_graph(graph_path)
            validate_graph(continued)
            self.assertEqual(continued["runtime"]["statuses"]["verify"], "ready")

    def test_node_history_can_continue_in_python(self):
        with tempfile.TemporaryDirectory() as directory:
            graph_path = Path(directory) / "含 空格.json"
            dev_graph.atomic_write(graph_path, valid_graph())
            self.run_node("init", graph_path)
            self.run_node("start", graph_path, "build")

            graph = dev_graph.load_graph(graph_path)
            graph = finish_node(graph, "build", "pass", "python accepted node history")
            dev_graph.atomic_write(graph_path, graph)

            self.run_node("validate", graph_path)
            status = json.loads(self.run_node("status", graph_path).stdout)
            self.assertEqual(status["ready"], ["verify"])

    def test_definition_hash_matches_between_runtimes(self):
        with tempfile.TemporaryDirectory() as directory:
            python_graph = initialize_graph(valid_graph())
            node_path = Path(directory) / "graph.json"
            dev_graph.atomic_write(node_path, valid_graph())
            self.run_node("init", node_path)
            node_graph = dev_graph.load_graph(node_path)

            self.assertEqual(
                python_graph["runtime"]["definition_hash"],
                node_graph["runtime"]["definition_hash"],
            )


if __name__ == "__main__":
    unittest.main()
