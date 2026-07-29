import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_skill():
    return (ROOT / "SKILL.md").read_text(encoding="utf-8")


def frontmatter(skill):
    match = re.match(r"^---\n(.*?)\n---\n", skill, flags=re.DOTALL)
    if not match:
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    return match.group(1)


class PublishedSkillQualityContract(unittest.TestCase):
    def test_frontmatter_exposes_distribution_metadata(self):
        metadata = frontmatter(read_skill())
        self.assertRegex(metadata, r"(?m)^license:\s*MIT$")
        self.assertRegex(metadata, r"(?m)^compatibility:\s*.+$")
        self.assertRegex(metadata, r"(?m)^allowed-tools:\s*Read Grep Glob$")
        self.assertRegex(metadata, r'(?m)^\s+version:\s*["\']1\.0\.1["\']$')
        self.assertIn("https://github.com/xincheng-1999/orchestrating-development-graphs", metadata)

    def test_skill_has_machine_discoverable_usage_sections(self):
        skill = read_skill()
        for heading in (
            "## When to Use",
            "## When Not to Use",
            "## Examples",
            "## Limitations",
            "## References",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, skill)

    def test_examples_use_language_tagged_code_fences(self):
        skill = read_skill()
        self.assertIn("```text", skill)
        self.assertIn("```powershell", skill)
        fences = [line for line in skill.splitlines() if line.startswith("```")]
        self.assertEqual(len(fences) % 2, 0, "code fences must be balanced")
        for opening in fences[::2]:
            self.assertRegex(opening, r"^```[a-zA-Z0-9_-]+$")

    def test_references_name_schema_and_companion_skills(self):
        skill = read_skill()
        self.assertIn("<SKILL_ROOT>/references/graph-schema.md", skill)
        for companion in (
            "superpowers:brainstorming",
            "superpowers:systematic-debugging",
            "superpowers:test-driven-development",
            "superpowers:verification-before-completion",
            "bounded-plan-execution",
        ):
            with self.subTest(companion=companion):
                self.assertIn(companion, skill)


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
