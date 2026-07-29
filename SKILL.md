---
name: orchestrating-development-graphs
description: Use when starting a code change, feature, bug fix, refactor, or build/configuration task where workflow intensity, approval gates, or delegation may otherwise be disproportionate to the task.
license: MIT
compatibility: Codex and Claude Code; Python 3.10+ or Node.js 18+ is required only for Complex graph execution.
allowed-tools: Read Grep Glob
metadata:
  version: "1.0.1"
  repository: https://github.com/xincheng-1999/orchestrating-development-graphs
---

# Orchestrating Development Graphs

## Overview

Choose the smallest reliable workflow. Use a persistent executable graph only when concrete risks make conditional gates, failure routes, and resumable state necessary.

User instructions and the nearest applicable host rule file—`AGENTS.md` in Codex or `CLAUDE.md` in Claude Code—override this Skill. Follow the host's normal rule-file discovery and precedence when both files are visible.

## When to Use

Use this Skill before every code change, feature, bug fix, refactor, build, dependency, or configuration task when the correct amount of process is not yet known. It is especially relevant when a task may involve approvals, public interfaces, persistence, migrations, concurrency, permissions, security, payments, resumable execution, or delegation.

## When Not to Use

Do not use this Skill for read-only explanation, status, review, research, or diagnosis that will not change code or configuration. Do not create a development graph merely because a task has several steps; only evidence-backed Complex work gets a persistent graph.

## Classify Before Acting

Use the lowest class supported by evidence and report the class, concrete signals, and route before implementation.

| Class | Signals | Route |
| --- | --- | --- |
| Simple | Clear, local, mechanical, low risk, easy rollback | `Implement -> focused Verify` |
| Standard | Bounded observable behavior change | compact `Spec -> approval -> Plan -> approval -> TDD batches -> Verify` |
| Complex | Cross-module flow, public API, persistence, migration, concurrency, permissions, security, payments, build/dependencies, or material ambiguity | approved Spec/Plan plus a persistent executable graph |

Simple tasks must not create a graph artifact. Do not create a Spec, Plan, worktree, commit, review pipeline, or subagent unless the user requests it or evidence forces reclassification. Implement and run the smallest fresh proof.

Standard tasks must not create a graph artifact. Save mutually linked documents at `<TARGET_ROOT>/docs/superpowers/specs/YYYY-MM-DD-<topic>.md` and `<TARGET_ROOT>/docs/superpowers/plans/YYYY-MM-DD-<topic>.md`; obtain approval after each. Keep the Plan to 3–5 acceptance-mapped steps.

Do not probe runtimes for Simple or Standard tasks. Runtime selection exists only to make a Complex execution graph executable.

## Resolve Skill and Target Roots

Before Standard or Complex work, resolve two distinct absolute directories:

- `SKILL_ROOT`: the directory containing this `SKILL.md`. Resolve it from the loaded Skill resource, never from the current working directory. Read `references/`, run `scripts/`, and access distributed `examples/` only beneath this root.
- `TARGET_ROOT`: the Git root of the repository being changed, otherwise the current directory. Write task Spec, Plan, graph JSON, runtime state, and SVG preview only beneath this root.

Never assume the target repository contains this Skill's executor. Substitute the resolved absolute paths when a command below contains `<SKILL_ROOT>` or `<TARGET_ROOT>`.

## Execute Complex Work as a Graph

For Complex work, keep orchestration artifacts under `<TARGET_ROOT>` and invoke the executor from `<SKILL_ROOT>`.

1. Write `<TARGET_ROOT>/docs/superpowers/specs/YYYY-MM-DD-<topic>.md` with current behavior, goals/non-goals, user behavior, interfaces/data flow, edge cases, risks, rollback, and acceptance criteria. Obtain approval.
2. Write a 3–5 step Plan and `<TARGET_ROOT>/docs/superpowers/graphs/YYYY-MM-DD-<topic>.json`. Link Spec, Plan, and graph both ways. Obtain approval for the Plan and graph.
3. **REQUIRED REFERENCE:** Read `<SKILL_ROOT>/references/graph-schema.md` before authoring or changing a graph.
4. Select one executor for the task and keep using it: prefer an actually runnable Python 3.10+ with `python "<SKILL_ROOT>/scripts/dev_graph.py"`; otherwise use Node.js 18+ with `node "<SKILL_ROOT>/scripts/dev_graph.mjs"`. Treat a broken Windows Store Python alias as unavailable. If both runtimes are unavailable, record a blocker and stop; never replace the executable ledger with a prose-only graph.
5. After authoring or changing a graph JSON definition, run `validate -> render` with the selected executor and confirm the same-name SVG exists before approval or execution. `init`, `start`, and outcome commands automatically refresh that SVG after state changes; JSON remains the source of truth.
6. Run `init` against the approved graph, then ask `ready` which nodes may run. Use `start` before work and exactly one outcome command—`pass`, `fail`, `block`, or `scope-change`—after work, with fresh evidence.
7. Follow only the node activated by the recorded edge. Do not manually rewrite runtime state, erase failed attempts, or continue down an inactive branch.
8. Before claiming completion, run `status` and require `completion: complete`, then perform the normal fresh verification pass.

The JSON graph is the execution ledger. Do not duplicate changing node status in the Plan. The executor validates orchestration evidence; it never runs tests, builds, migrations, deployments, or arbitrary task commands.

If the task changes the graph executor itself and no prior executor exists, the first validator node may bootstrap under an approved Spec and Plan. As soon as the executor works, initialize the graph and replay that node with fresh RED/GREEN evidence. No later node may bypass the executor.

## Route Node Handlers

When a named companion Skill is available in the current host, load it as required below. When it is unavailable, perform the stated discipline directly in the current Agent; a missing optional companion name is not a blocker.

- Material ambiguity: use `superpowers:brainstorming` when available; otherwise clarify goals, constraints, alternatives, and acceptance before finalizing the Spec.
- Defect or unexpected behavior: **REQUIRED WHEN AVAILABLE:** use `superpowers:systematic-debugging`; otherwise reproduce, gather evidence, isolate the root cause, then propose or implement a fix.
- Approved multi-step work: use `superpowers:writing-plans` when available; otherwise write the 3–5 acceptance-mapped steps directly. Reject automatic commits, worktrees, or per-task agents.
- Testable Standard/Complex behavior: **REQUIRED WHEN AVAILABLE:** use `superpowers:test-driven-development`; otherwise run the same RED -> GREEN -> REFACTOR cycle directly.
- Approved Plan: use `bounded-plan-execution` when available; otherwise execute the approved steps sequentially in the main Agent and record fresh verification after each batch.
- Completion claim: **REQUIRED WHEN AVAILABLE:** use `superpowers:verification-before-completion`; otherwise run fresh focused and integration verification before reporting success.
- Independent review: use `superpowers:requesting-code-review` when available and only for security, concurrency, permissions, migrations, or payments.
- Worktrees, commits, PRs, and branch finishing: use only when requested or repository-required.

Never default to `superpowers:subagent-driven-development`; use it only when the user explicitly selects its per-task multi-agent pipeline.

## Keep Host Compatibility

The portable Skill consists of `SKILL.md`, `references/`, and `scripts/`. `agents/openai.yaml` supplies Codex display metadata only; Claude Code may ignore it without losing classification or graph execution.

Claude Code discovers the Skill from a user or project `.claude/skills/orchestrating-development-graphs` directory and may invoke it as `/orchestrating-development-graphs` or through a matching natural-language request. Codex uses its configured Skill directory and `$orchestrating-development-graphs`.

Only a runnable Python or Node.js executor is a hard dependency for Complex graph execution. Superpowers and `bounded-plan-execution` are optional companion Skills, not prerequisites. They improve individual node handling when installed; the fallback rules above keep the core classifier, state machine, evidence ledger, and SVG preview usable without them.

## Bound Delegation

Default to zero subagents. Delegate only a bounded outcome independent of evolving integration context, with disjoint ownership or read-only scope and positive coordination value. A subagent statement is not gate evidence.

Use at most two subagents concurrently and three per task. These are ceilings. Explain the benefit and obtain approval before exceeding them. Never create implementer/reviewer/fixer pipelines per Plan item.

## Enforce Evidence and Failure Routes

Every nontrivial graph node records inputs, owner, outputs, pass condition, and failure destination. Gates and approvals cannot pass without evidence. Use test, compiler/type/lint/build, runtime, business, database, or explicit user-approval evidence.

On an ordinary failure, record `fail` first, follow the activated diagnostic or rework node, rerun the original gate, and preserve every attempt. On a material scope change, record `scope-change`, update Spec/Plan/graph, obtain approval, then reinitialize. Never weaken a pass condition to make a gate green.

Stop and simplify when a Simple or Standard task starts creating a graph, task count determines agent count, Git actions lack authority, loops exceed their bound, or success relies only on an Agent assertion.

## Examples

Classify from evidence, not from prompt length or the label "Complex":

```text
Rename a local variable and run one focused test
=> Simple: Implement -> focused Verify

Add bounded validation behavior to one service
=> Standard: Spec -> approval -> Plan -> approval -> TDD batches -> Verify

Migrate persisted data while preserving a public API and rollback path
=> Complex: approved Spec/Plan -> executable graph -> evidence gates
```

For a Complex graph on Windows, resolve both roots first, then validate and render with one available executor:

```powershell
$skillRoot = "C:\absolute\path\to\orchestrating-development-graphs"
$targetRoot = "C:\absolute\path\to\target-repository"
$graph = Join-Path $targetRoot "docs\superpowers\graphs\2026-07-29-migration.json"

node (Join-Path $skillRoot "scripts\dev_graph.mjs") validate $graph
node (Join-Path $skillRoot "scripts\dev_graph.mjs") render $graph
```

## Limitations

- The executor validates and records orchestration state; it does not run tests, builds, migrations, deployments, or arbitrary task commands.
- JSON is the source of truth; the SVG is a generated preview and cannot be used to update graph state.
- Complex execution requires Python 3.10+ or Node.js 18+. Simple and Standard routing requires neither runtime.
- Companion Skills improve node handling but are optional; host rules and explicit user instructions always take precedence.

## References

- **REQUIRED FOR GRAPH AUTHORING:** `<SKILL_ROOT>/references/graph-schema.md`
- Optional companion Skills: `superpowers:brainstorming`, `superpowers:systematic-debugging`, `superpowers:writing-plans`, `superpowers:test-driven-development`, `bounded-plan-execution`, `superpowers:verification-before-completion`, and `superpowers:requesting-code-review`.
- Distribution and installation guide: `README.md` and `README.zh-CN.md` in the repository root.
