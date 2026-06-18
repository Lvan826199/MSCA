# MEMORY.md

本文件用于记录跨会话、跨机器共享的项目记忆，只写非敏感内容。

## 当前约定

- `CLAUDE.md` 是唯一完整 AI 助手规则源。
- `AGENTS.md` 只作为 Codex 入口，引导 Codex 读取并遵守 `CLAUDE.md`。
- `memory/ai_step.md` 继续作为开发操作与验证结果的追溯日志。
- `.claude/settings.local.json`、`.claude/worktrees/`、`.agent/`、`.agents/`、`.codex/`、`.Codex/` 仅用于本机工具私有配置，不作为跨工具同步源。
- `.claude/` 下明确作为项目共享资产维护的 skills 可以继续入库。

## 禁止记录

- token、账号、密钥、证书、Cookie 等敏感凭据。
- 机器私有路径、权限白名单、本地缓存目录。
- 只对某台设备或某个账号有效的临时状态。
