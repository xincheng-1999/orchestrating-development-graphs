import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ClaudeCodeCompatibilityContract(unittest.TestCase):
    def test_skill_recognizes_both_host_rule_files(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`AGENTS.md`", skill)
        self.assertIn("`CLAUDE.md`", skill)

    def test_readmes_document_claude_code_installation(self):
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(name=name):
                readme = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn(".claude/skills/orchestrating-development-graphs", readme)
                self.assertIn("examples/CLAUDE.md", readme)

    def test_host_rule_examples_exist_and_select_the_graph_skill_first(self):
        for name in ("AGENTS.md", "CLAUDE.md"):
            with self.subTest(name=name):
                example = ROOT / "examples" / name
                self.assertTrue(example.is_file(), f"missing {example}")
                content = example.read_text(encoding="utf-8")
                self.assertIn("orchestrating-development-graphs", content)
                self.assertIn("before", content.lower())

    def test_claude_compatibility_notes_cover_optional_companion_skills(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Claude Code compatibility", readme)
        self.assertIn("agents/openai.yaml", readme)
        self.assertIn("companion skills", readme.lower())

    def test_dependency_contract_distinguishes_hard_and_optional_requirements(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("Superpowers", english)
        self.assertIn("not a prerequisite", english)
        self.assertIn("Superpowers", chinese)
        self.assertIn("不是前置依赖", chinese)

    def test_skill_resolves_executor_from_skill_root_not_target_repository(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("SKILL_ROOT", skill)
        self.assertIn("TARGET_ROOT", skill)
        self.assertIn("directory containing this `SKILL.md`", skill)
        self.assertIn("<SKILL_ROOT>/scripts/dev_graph.py", skill)
        self.assertIn("<SKILL_ROOT>/scripts/dev_graph.mjs", skill)

    def test_installation_docs_cover_fresh_install_update_project_and_smoke_test(self):
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(name=name):
                readme = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("New-Item", readme)
                self.assertIn("mkdir -p", readme)
                self.assertIn("pull --ff-only", readme)
                self.assertIn("git submodule add", readme)
                self.assertIn("examples/development-graph.json", readme)
                self.assertIn("VALID:", readme)


if __name__ == "__main__":
    unittest.main()
