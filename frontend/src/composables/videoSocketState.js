export function createVideoSocketCloseHandler({ clearSocket, setConnected, cleanup }) {
  return () => {
    setConnected(false)
    clearSocket()
    cleanup()
  }
}
