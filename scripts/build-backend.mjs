import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const root = process.cwd()
const backendDir = path.join(root, "backend")
const distDir = path.join(root, "dist", "backend")
const resourcesDir = path.join(root, "resources")

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

async function ensureNuitka() {
  try {
    await run("uv", ["run", "python", "-c", "import nuitka"], backendDir)
  } catch {
    await run("uv", ["add", "--dev", "nuitka", "ordered-set"], backendDir)
  }
}

console.log("[build] 开始编译后端...")
await ensureNuitka()

await run(
  "uv",
  [
    "run",
    "python",
    "-m",
    "nuitka",
    "--standalone",
    "--onefile",
    "--output-filename=msca-backend.exe",
    "--include-package=app",
    "--include-package=uvicorn",
    "--include-package=fastapi",
    "--follow-imports",
    "__main__.py"
  ],
  backendDir
)

mkdirSync(distDir, { recursive: true })
mkdirSync(resourcesDir, { recursive: true })

const backendExe = path.join(backendDir, "msca-backend.exe")
const fallbackExe = path.join(backendDir, "__main__.exe")
const outputExe = path.join(distDir, "msca-backend.exe")
const sourceExe = existsSync(backendExe) ? backendExe : fallbackExe

if (!existsSync(sourceExe)) {
  throw new Error("未找到编译产物 msca-backend.exe")
}

rmSync(outputExe, { force: true })
copyFileSync(sourceExe, outputExe)
copyFileSync(outputExe, path.join(resourcesDir, "msca-backend.exe"))

console.log(`[build] 后端编译完成 -> ${outputExe}`)
