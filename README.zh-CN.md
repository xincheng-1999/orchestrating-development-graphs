# 开发图编排 Skill

[English](README.md)

这是一个 Codex Skill：先判断开发任务的复杂度，再选择足够可靠且不过度的工作流。只有真正复杂的改动才创建持久化、可执行的开发图。

它不会把所有任务都塞进同一套重流程：

| 分类 | 典型信号 | 路线 |
| --- | --- | --- |
| Simple | 局部、机械、低风险、容易回滚 | `Implement -> focused Verify` |
| Standard | 范围明确的可观察行为变化 | `Spec -> Plan -> TDD batches -> Verify` |
| Complex | 跨模块、持久化、迁移、并发、权限、安全、构建或依赖风险 | 已审批 Spec/Plan + 可执行 JSON Graph |

## 为什么这是真正的 Graph Engineering

Complex 路线中的 JSON 不是用来展示的静态流程图，而是持久化状态机：

- 记录 `ready/running/passed/failed/blocked/skipped` 状态；
- 只允许沿 `pass/fail/blocked/scope_change` 边迁移；
- 重试和返工循环必须有明确上限；
- 历史只追加，并通过 SHA-256 哈希链防止静默篡改；
- 成功路径不能绕过必要门禁；
- 自动生成并刷新零依赖 SVG 预览。

```mermaid
flowchart LR
    A["实现"] -->|通过| B{"验证门禁"}
    B -->|通过| C["成功"]
    B -->|失败| D["返工"]
    D -->|修复后重跑，次数有限| B
    A -->|范围变化| E["重新审批"]
    B -->|范围变化| E
```

## 环境要求

Complex 图执行至少需要一个运行时：

- 优先使用 Python 3.10+；
- Python 不可用时回退 Node.js 18+。

Simple 和 Standard 不探测运行时。两个执行器都只使用标准库，没有 pip 或 npm 运行依赖。

Skill 会按节点场景引用以下配套 Skill，仓库不会复制它们的源码：

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:systematic-debugging`
- `superpowers:verification-before-completion`
- 可用时使用 `bounded-plan-execution`

## 安装

可以让 Codex 使用 `skill-installer` 安装本仓库，也可以直接克隆。

PowerShell：

```powershell
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git `
  "$env:USERPROFILE\.codex\skills\orchestrating-development-graphs"
```

macOS/Linux：

```bash
git clone https://github.com/xincheng-1999/orchestrating-development-graphs.git \
  "$HOME/.codex/skills/orchestrating-development-graphs"
```

安装后重启 Codex 或新建任务，让 Skill 列表重新加载。

## 命令

Python 和 Node.js 提供相同命令：

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

例如：

```powershell
python scripts/dev_graph.py validate docs/superpowers/graphs/change.json
python scripts/dev_graph.py render docs/superpowers/graphs/change.json

node scripts/dev_graph.mjs init docs/superpowers/graphs/change.json
node scripts/dev_graph.mjs ready docs/superpowers/graphs/change.json
```

`render path/name.json` 默认生成 `path/name.svg`。`init/start/pass/fail/block/scope-change` 修改状态时也会自动刷新同名 SVG。

## 安全边界

执行器只验证和持久化编排状态，不执行测试、构建、迁移、部署、Shell 或任意任务命令。Node.js 实现明确不导入 `node:child_process`。

它会拒绝无上限循环、缺少失败路线的 gate、绕过必要门禁的成功路径、非法状态快照、被篡改的历史链以及超出双运行时安全整数范围的重试次数。

## 测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_dev_graph.mjs
```

测试覆盖静态校验、状态迁移、重试上限、重新审批、篡改检测、完成判定、SVG 安全、自动预览、规范化哈希和 Python/Node 双向互操作。

## License

[MIT](LICENSE)
