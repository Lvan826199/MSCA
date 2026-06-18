import { mkdirSync } from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const root = process.cwd()
const backendDir = path.join(root, "backend")
const uvCacheDir = process.env.UV_CACHE_DIR || path.join(root, ".uv-cache")
const uvCommand = process.platform === "win32" ? "uv.exe" : "uv"

mkdirSync(uvCacheDir, { recursive: true })

const child = spawn(
  uvCommand,
  ["run", "python", "-m", "unittest", "discover", "-s", "tests"],
  {
    cwd: backendDir,
    stdio: "inherit",
    shell: false,
    env: {
      ...process.env,
      UV_CACHE_DIR: uvCacheDir,
    },
  }
)

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`[test-backend] backend tests stopped by signal ${signal}`)
    process.exit(1)
  }
  process.exit(code ?? 1)
})

child.on("error", (err) => {
  console.error(`[test-backend] failed to start backend tests: ${err.message}`)
  process.exit(1)
})

