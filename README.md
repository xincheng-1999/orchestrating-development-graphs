# Orchestrating Development Graphs

[简体中文](README.zh-CN.md)

A Codex and Claude Code skill that selects the smallest reliable development workflow and uses a persistent executable graph only when a change is genuinely complex.

This is not a wrapper that sends every task through the same heavyweight pipeline:

| Class | Typical signals | Route |
| --- | --- | --- |
| Simple | Local, mechanical, low risk, easy rollback | `Implement -> focused Verify` |
| Standard | Bounded observable behavior change | `Spec -> Plan -> TDD batches -> Verify` |
| Complex | Cross-module flow, persistence, migration, concurrency, permissions, security, build/dependency risk | Approved Spec/Plan plus an executable JSON graph |

## What makes the Complex route executable

The JSON graph is a persistent state machine, not a diagram-only artifact. It records:

- ready, running, passed, failed, blocked, and skipped node states;
- explicit pass, fail, blocked, and scope-change transitions;
- bounded retry and rework loops;
- append-only, SHA-256-chained evidence history;
- required gates that cannot be bypassed on a successful path;
- a synchronized, dependency-free SVG preview.

```mermaid
flowchart LR
    A["Implement"] -->|pass| B{"Verify"}
    B -->|pass| C["Success"]
    B -->|fail| D["Rework"]
    D -->|pass, bounded| B
    A -->|scope change| E["Re-approval"]
    B -->|scope change| E
```

## Requirements

Complex graph execution needs one of:

- Python 3.10 or newer, preferred when available; or
- Node.js 18 or newer, used as the fallback.

Simple and Standard tasks do not probe either runtime. Both executors use only their standard libraries; there are no pip or npm runtime dependencies.

The orchestration skill routes node work to these companion skills when relevant:

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:systematic-debugging`
- `superpowers:verification-before-completion`
- `bounded-plan-execution`, when available

Install those separately if your host provides them. They are referenced by name and are not vendored here. If a companion skill is unavailable, the current agent applies the same discipline directly; only Python or Node.js is required for Complex graph execution.

## Installation

### Codex

Ask Codex to install this repository with `skill-installer`, or clone it directly.

PowerShell:

```powershell
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git `
  "$env:USERPROFILE\.codex\skills\orchestrating-development-graphs"
```

macOS/Linux:

```bash
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git \
  "$HOME/.codex/skills/orchestrating-development-graphs"
```

Restart Codex or begin a new task after installation so the skill catalog is refreshed.

### Claude Code

Install it as a user skill on PowerShell:

```powershell
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git `
  "$env:USERPROFILE/.claude/skills/orchestrating-development-graphs"
```

On macOS/Linux:

```bash
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git \
  "$HOME/.claude/skills/orchestrating-development-graphs"
```

For project-only installation, clone or add the repository at `.claude/skills/orchestrating-development-graphs` inside that project. Start a new Claude Code session, then invoke `/orchestrating-development-graphs` or ask Claude to classify a development task with the skill.

To make routing automatic for every development change, copy the relevant rule template into your repository root:

- Codex: [`examples/AGENTS.md`](examples/AGENTS.md)
- Claude Code: [`examples/CLAUDE.md`](examples/CLAUDE.md)

## Claude Code compatibility

- Claude Code reads the standard `SKILL.md`, `references/`, and `scripts/` content directly.
- `agents/openai.yaml` is optional Codex display metadata; Claude Code can ignore it.
- The named companion skills are optional. Install Superpowers or equivalent skills if desired; otherwise this Skill tells Claude to apply the same planning, debugging, TDD, and verification disciplines directly.
- Python 3.10+ and Node.js 18+ commands are host-independent. No pip or npm packages are required.
- Repository instructions belong in `CLAUDE.md` for Claude Code and `AGENTS.md` for Codex. The supplied examples keep their routing policy aligned.

## CLI

Python and Node.js expose the same graph commands:

```text
init <graph> [--output <path>] [--approval-evidence <text>]
validate <graph>
ready <graph>
start <graph> <node>
pass <graph> <node> --evidence <text> [--output <text>]
fail <graph> <node> --evidence <text> [--output <text>]
block <graph> <node> --evidence <text> [--output <text>]
scope-change <graph> <node> --evidence <text> [--output <text>]
status <graph>
render <graph> [--output <preview.svg>]
```

Examples:

```powershell
python scripts/dev_graph.py validate docs/superpowers/graphs/change.json
python scripts/dev_graph.py render docs/superpowers/graphs/change.json

node scripts/dev_graph.mjs init docs/superpowers/graphs/change.json
node scripts/dev_graph.mjs ready docs/superpowers/graphs/change.json
```

Without `--output`, `render path/name.json` creates `path/name.svg`. Mutating commands also refresh the same-name SVG automatically so the preview follows runtime state.

## Safety boundaries

The executor validates orchestration state only. It never runs tests, builds, migrations, deployments, shells, or arbitrary task commands. In particular, the Node.js implementation does not import `node:child_process`.

Graph definitions reject unbounded cycles, missing gate failure routes, required-gate bypasses, invalid snapshots, tampered history chains, and retry counters outside the shared safe-integer range.

## Tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_dev_graph.mjs
```

The suite covers static validation, state transitions, retry limits, re-approval, tamper detection, completion, SVG safety, automatic preview refresh, canonical hashes, and Python/Node interoperability.

## Repository layout

```text
SKILL.md
agents/openai.yaml
examples/AGENTS.md
examples/CLAUDE.md
references/graph-schema.md
scripts/dev_graph.py
scripts/dev_graph.mjs
tests/test_dev_graph.py
tests/test_dev_graph.mjs
tests/test_skill_contract.py
```

## License

[MIT](LICENSE)
