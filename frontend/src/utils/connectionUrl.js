export function normalizeHttpBaseUrl(url) {
  const trimmed = String(url || "").trim().replace(/\/+$/, "")
  if (!trimmed) return ""
  if (trimmed.startsWith("wss://")) return `https://${trimmed.slice(6)}`
  if (trimmed.startsWith("ws://")) return `http://${trimmed.slice(5)}`
  if (/^https?:\/\//.test(trimmed)) return trimmed
  return `https://${trimmed}`
}

export function toWsBaseUrl(url) {
  return String(url || "").replace(/^http/, "ws")
}
