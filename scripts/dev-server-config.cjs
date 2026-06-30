const fs = require("node:fs")
const path = require("node:path")

function readDevServerConfig(rootDir = path.resolve(__dirname, "..")) {
  const configPath = path.join(rootDir, "config", "dev-server.json")
  let rawConfig
  try {
    rawConfig = JSON.parse(fs.readFileSync(configPath, "utf8"))
  } catch (err) {
    throw new Error(`Failed to read ${configPath}: ${err.message}`)
  }

  const frontend = rawConfig.frontend || {}
  const backend = rawConfig.backend || {}
  return {
    frontend: {
      host: readHost(frontend.host, "frontend.host"),
      port: readPort(frontend.port, "frontend.port"),
      portSearchAttempts: readPositiveInteger(
        frontend.portSearchAttempts,
        "frontend.portSearchAttempts"
      ),
    },
    backend: {
      host: readHost(backend.host, "backend.host"),
      port: readPort(backend.port, "backend.port"),
    },
  }
}

function getFrontendDevServerConfig(env = process.env, rootDir = path.resolve(__dirname, "..")) {
  const config = readDevServerConfig(rootDir).frontend
  return {
    host: readHost(env.MSCA_FRONTEND_HOST || config.host, "MSCA_FRONTEND_HOST"),
    port: readPort(env.MSCA_FRONTEND_PORT || config.port, "MSCA_FRONTEND_PORT"),
    portSearchAttempts: readPositiveInteger(
      env.MSCA_FRONTEND_PORT_ATTEMPTS || config.portSearchAttempts,
      "MSCA_FRONTEND_PORT_ATTEMPTS"
    ),
  }
}

function getBackendDevServerConfig(env = process.env, rootDir = path.resolve(__dirname, "..")) {
  const config = readDevServerConfig(rootDir).backend
  return {
    host: readHost(env.MSCA_BACKEND_HOST || config.host, "MSCA_BACKEND_HOST"),
    port: readPort(env.MSCA_BACKEND_PORT || config.port, "MSCA_BACKEND_PORT"),
  }
}

function buildFrontendDevServerUrl(config) {
  return `http://${config.host}:${config.port}`
}

function readHost(value, name) {
  const host = String(value || "").trim()
  if (!host) {
    throw new Error(`${name} must not be empty`)
  }
  return host
}

function readPort(value, name) {
  const port = readPositiveInteger(value, name)
  if (port > 65535) {
    throw new Error(`${name} must be between 1 and 65535`)
  }
  return port
}

function readPositiveInteger(value, name) {
  const text = String(value || "").trim()
  if (!/^\d+$/.test(text)) {
    throw new Error(`${name} must be a positive integer`)
  }
  const number = Number(text)
  if (!Number.isSafeInteger(number) || number <= 0) {
    throw new Error(`${name} must be a positive integer`)
  }
  return number
}

module.exports = {
  buildFrontendDevServerUrl,
  getBackendDevServerConfig,
  getFrontendDevServerConfig,
  readDevServerConfig,
}
