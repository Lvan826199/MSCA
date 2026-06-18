# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## 唯一规则源

本仓库的完整 AI 助手规则以 `CLAUDE.md` 为唯一权威来源。

Codex 在本仓库开始任何工作前，必须先读取并遵守 `CLAUDE.md`。`CLAUDE.md` 中出现的 “Claude Code” / “Claude” 对 Codex 等价适用；其中涉及本地工具配置目录的 `.claude` / `~/.claude`，在 Codex 场景下等价理解为 `.Codex` / `~/.Codex`，除非某条规则明确只针对 Claude Code。

以后新增或调整助手规则时，只修改 `CLAUDE.md`，不要在 `AGENTS.md` 复制规则正文。
