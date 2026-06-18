import { readFileSync } from "node:fs"
import path from "node:path"

const root = process.cwd()
const agentsPath = path.join(root, "AGENTS.md")
const claudePath = path.join(root, "CLAUDE.md")

const agents = readFileSync(agentsPath, "utf8").replace(/\r\n/g, "\n").trim()
readFileSync(claudePath, "utf8")

const requiredSnippets = [
  "# AGENTS.md",
  "This file provides guidance to Codex when working with code in this repository.",
  "## 唯一规则源",
  "本仓库的完整 AI 助手规则以 `CLAUDE.md` 为唯一权威来源。",
  "Codex 在本仓库开始任何工作前，必须先读取并遵守 `CLAUDE.md`。",
  "以后新增或调整助手规则时，只修改 `CLAUDE.md`，不要在 `AGENTS.md` 复制规则正文。",
]

const missing = requiredSnippets.filter((snippet) => !agents.includes(snippet))
const tooLong = agents.split("\n").length > 24

if (missing.length > 0 || tooLong) {
  if (missing.length > 0) {
    console.error("AGENTS.md is missing required entry snippets:")
    for (const snippet of missing) {
      console.error(`- ${snippet}`)
    }
  }
  if (tooLong) {
    console.error("AGENTS.md should remain a short Codex entry, not a copy of CLAUDE.md.")
  }
  process.exit(1)
}

console.log("AGENTS.md correctly points Codex to CLAUDE.md.")
