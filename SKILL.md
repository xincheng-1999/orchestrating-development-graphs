---
name: orchestrating-development-graphs
description: Use when starting a code change, feature, bug fix, refactor, or build/configuration task where workflow intensity, approval gates, or delegation may otherwise be disproportionate to the task.
---

# Orchestrating Development Graphs

## Overview

Choose the smallest reliable workflow. Use a persistent executable graph only when concrete risks make conditional gates, failure routes, and resumable state necessary.

User instructions and the nearest applicable `AGENTS.md` override this Skill.

## Classify Before Acting

Use the lowest class supported by evidence and report the class, concrete signals, and route before implementation.

| Class | Signals | Route |
| --- | --- | --- |
| Simple | Clear, local, mechanical, low risk, easy rollback | `Implement -> focused Verify` |
| Standard | Bounded observable behavior change | compact `Spec -> approval -> Plan -> approval -> TDD batches -> Verify` |
| Complex | Cross-module flow, public API, persistence, migration, concurrency, permissions, security, payments, build/dependencies, or material ambiguity | approved Spec/Plan plus a persistent executable graph |

Simple tasks must not create a graph artifact. Do not create a Spec, Plan, worktree, commit, review pipeline, or subagent unless the user requests it or evidence forces reclassification. Implement and run the smallest fresh proof.

Standard tasks must not create a graph artifact. Use the Git root, otherwise the current directory. Save mutually linked documents at `docs/superpowers/specs/YYYY-MM-DD-<topic>.md` and `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`; obtain approval after each. Keep the Plan to 3–5 acceptance-mapped steps.

Do not probe runtimes for Simple or Standard tasks. Runtime selection exists only to make a Complex execution graph executable.

## Execute Complex Work as a Graph

For Complex work, use the Git root, otherwise the current directory.

1. Write `docs/superpowers/specs/YYYY-MM-DD-<topic>.md` with current behavior, goals/non-goals, user behavior, interfaces/data flow, edge cases, risks, rollback, and acceptance criteria. Obtain approval.
2. Write a 3–5 step Plan and `docs/superpowers/graphs/YYYY-MM-DD-<topic>.json`. Link Spec, Plan, and graph both ways. Obtain approval for the Plan and graph.
3. **REQUIRED REFERENCE:** Read `references/graph-schema.md` before authoring or changing a graph.
4. Select one executor for the task and keep using it: prefer an actually runnable Python 3.10+ with `scripts/dev_graph.py`; otherwise use Node.js 18+ with `scripts/dev_graph.mjs`. Treat a broken Windows Store Python alias as unavailable. If both runtimes are unavailable, record a blocker and stop; never replace the executable ledger with a prose-only graph.
5. After authoring or changing a graph JSON definition, run `validate -> render` with the selected executor and confirm the same-name SVG exists before approval or execution. `init`, `start`, and outcome commands automatically refresh that SVG after state changes; JSON remains the source of truth.
6. Run `init` against the approved graph, then ask `ready` which nodes may run. Use `start` before work and exactly one outcome command—`pass`, `fail`, `block`, or `scope-change`—after work, with fresh evidence.
7. Follow only the node activated by the recorded edge. Do not manually rewrite runtime state, erase failed attempts, or continue down an inactive branch.
8. Before claiming completion, run `status` and require `completion: complete`, then perform the normal fresh verification pass.

The JSON graph is the execution ledger. Do not duplicate changing node status in the Plan. The executor validates orchestration evidence; it never runs tests, builds, migrations, deployments, or arbitrary task commands.

If the task changes the graph executor itself and no prior executor exists, the first validator node may bootstrap under an approved Spec and Plan. As soon as the executor works, initialize the graph and replay that node with fresh RED/GREEN evidence. No later node may bypass the executor.

## Route Node Handlers

- Material ambiguity: use `superpowers:brainstorming` before finalizing the Spec.
- Defect or unexpected behavior: **REQUIRED SUB-SKILL:** use `superpowers:systematic-debugging` before proposing or implementing a fix.
- Approved multi-step work: use `superpowers:writing-plans`; keep 3–5 steps and reject automatic commits, worktrees, or per-task agents.
- Testable Standard/Complex behavior: **REQUIRED SUB-SKILL:** use `superpowers:test-driven-development`.
- Approved Plan: **REQUIRED SUB-SKILL:** use `bounded-plan-execution` when available; the main Agent owns implementation and integration.
- Completion claim: **REQUIRED SUB-SKILL:** use `superpowers:verification-before-completion`.
- Independent review: use `superpowers:requesting-code-review` only for security, concurrency, permissions, migrations, or payments.
- Worktrees, commits, PRs, and branch finishing: use only when requested or repository-required.

Never default to `superpowers:subagent-driven-development`; use it only when the user explicitly selects its per-task multi-agent pipeline.

## Bound Delegation

Default to zero subagents. Delegate only a bounded outcome independent of evolving integration context, with disjoint ownership or read-only scope and positive coordination value. A subagent statement is not gate evidence.

Use at most two subagents concurrently and three per task. These are ceilings. Explain the benefit and obtain approval before exceeding them. Never create implementer/reviewer/fixer pipelines per Plan item.

## Enforce Evidence and Failure Routes

Every nontrivial graph node records inputs, owner, outputs, pass condition, and failure destination. Gates and approvals cannot pass without evidence. Use test, compiler/type/lint/build, runtime, business, database, or explicit user-approval evidence.

On an ordinary failure, record `fail` first, follow the activated diagnostic or rework node, rerun the original gate, and preserve every attempt. On a material scope change, record `scope-change`, update Spec/Plan/graph, obtain approval, then reinitialize. Never weaken a pass condition to make a gate green.

Stop and simplify when a Simple or Standard task starts creating a graph, task count determines agent count, Git actions lack authority, loops exceed their bound, or success relies only on an Agent assertion.
