import { readFileSync, statSync, writeFileSync } from "node:fs"
import path from "node:path"

const root = process.cwd()
const docs = {
  claude: path.join(root, "CLAUDE.md"),
  agents: path.join(root, "AGENTS.md"),
}

const variants = {
  title: {
    claude: "# CLAUDE.md",
    agents: "# AGENTS.md",
    token: "# {{AGENT_DOC_NAME}}",
  },
  skillPath: {
    claude: "`~/.claude/skills/planning-with-files/`",
    agents: "`~/.Codex/skills/planning-with-files/`",
    token: "`{{PLANNING_SKILL_PATH}}`",
  },
  docLink: {
    claude: "(`CLAUDE.md`)",
    agents: "(`AGENTS.md`)",
    token: "(`{{AGENT_DOC_NAME}}`)",
  },
}

function parseArgs() {
  const args = new Set(process.argv.slice(2))
  return {
    check: args.has("--check"),
    from: args.has("--from=claude") ? "claude" : args.has("--from=agents") ? "agents" : null,
  }
}

function replaceAll(text, from, to) {
  return text.split(from).join(to)
}

function toCommon(text, kind) {
  let common = text
  for (const item of Object.values(variants)) {
    common = replaceAll(common, item[kind], item.token)
  }
  return common
}

function render(common, kind) {
  let text = common
  for (const item of Object.values(variants)) {
    text = replaceAll(text, item.token, item[kind])
  }
  return text
}

function read(kind) {
  return readFileSync(docs[kind], "utf8")
}

function newestDoc() {
  const claudeTime = statSync(docs.claude).mtimeMs
  const agentsTime = statSync(docs.agents).mtimeMs
  return agentsTime > claudeTime ? "agents" : "claude"
}

const { check, from } = parseArgs()
const source = from || newestDoc()
const target = source === "claude" ? "agents" : "claude"
const sourceCommon = toCommon(read(source), source)
const expectedTarget = render(sourceCommon, target)

if (check) {
  const currentTarget = read(target)
  const commonMatches = toCommon(read("claude"), "claude") === toCommon(read("agents"), "agents")
  const targetMatches = currentTarget === expectedTarget
  if (!commonMatches || !targetMatches) {
    console.error(
      `Agent docs are out of sync. Run: npm run sync:agents -- --from=${source}`
    )
    process.exit(1)
  }
  console.log("Agent docs are in sync.")
} else {
  writeFileSync(docs[target], expectedTarget, "utf8")
  console.log(`Synced ${path.basename(docs[target])} from ${path.basename(docs[source])}.`)
}

