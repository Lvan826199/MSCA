import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const root = process.cwd()

function run(command, args, cwd = root) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: "inherit", shell: false })
    child.on("exit", (code) => {
      if (code === 0) {
        resolve()
      } else {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`))
      }
    })
    child.on("error", reject)
  })
}

const frontendDir = path.join(root, "frontend")
const sourceDir = path.join(frontendDir, "dist")
const targetDir = path.join(root, "dist", "web")

await run("npm.cmd", ["run", "build"], frontendDir)

rmSync(targetDir, { recursive: true, force: true })
mkdirSync(targetDir, { recursive: true })

if (existsSync(sourceDir)) {
  cpSync(sourceDir, targetDir, { recursive: true })
}
