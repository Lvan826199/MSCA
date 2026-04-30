import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs"
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

const buildDir = path.join(backendDir, "build", "nuitka")
rmSync(buildDir, { recursive: true, force: true })
mkdirSync(buildDir, { recursive: true })

await run(
  "uv",
  [
    "run",
    "python",
    "-m",
    "nuitka",
    "--standalone",
    "--assume-yes-for-downloads",
    "--output-dir=build/nuitka",
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

const backendExe = process.platform === "win32"
  ? path.join(buildDir, "msca-backend.dist", "msca-backend.exe")
  : path.join(buildDir, "msca-backend.dist", "msca-backend")
const fallbackExe = process.platform === "win32"
  ? path.join(buildDir, "__main__.dist", "msca-backend.exe")
  : path.join(buildDir, "__main__.dist", "msca-backend")
const distRuntimeDir = path.join(distDir, "msca-backend")
const resourceRuntimeDir = path.join(resourcesDir, "msca-backend")
const sourceRuntimeDir = existsSync(path.join(buildDir, "msca-backend.dist"))
  ? path.join(buildDir, "msca-backend.dist")
  : path.join(buildDir, "__main__.dist")
const outputExe = path.join(distRuntimeDir, process.platform === "win32" ? "msca-backend.exe" : "msca-backend")
const resourceExe = path.join(resourceRuntimeDir, process.platform === "win32" ? "msca-backend.exe" : "msca-backend")
const sourceExe = existsSync(backendExe) ? backendExe : fallbackExe

if (!existsSync(sourceExe)) {
  throw new Error("未找到编译产物 msca-backend.exe")
}

rmSync(distRuntimeDir, { recursive: true, force: true })
rmSync(resourceRuntimeDir, { recursive: true, force: true })
cpSync(sourceRuntimeDir, distRuntimeDir, { recursive: true })
cpSync(sourceRuntimeDir, resourceRuntimeDir, { recursive: true })

if (!existsSync(outputExe) || !existsSync(resourceExe)) {
  throw new Error("后端运行时目录复制不完整")
}

console.log(`[build] 后端编译完成 -> ${outputExe}`)
