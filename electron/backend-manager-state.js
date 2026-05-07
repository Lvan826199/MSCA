function shouldRestartBackend({ stopping, restartCount, maxRestartAttempts }) {
  return !stopping && restartCount < maxRestartAttempts
}

function backendStatus({ port, running }) {
  return { port, running }
}

module.exports = { shouldRestartBackend, backendStatus }
