# Adaptive Development Workflow

- Before any other development process skill, use `$orchestrating-development-graphs` to classify and route every code, feature, bug-fix, refactor, build, dependency, or configuration change.
- User instructions and the nearest repository rules override Skill defaults.
- Simple tasks use only `Implement -> focused Verify`. Do not create a Spec, Plan, graph, worktree, commit, PR, review pipeline, or subagent unless the user requests it or evidence forces reclassification.
- Do not create worktrees, commits, pushes, or pull requests unless the user explicitly requests them or repository policy requires them.
