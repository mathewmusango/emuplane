// IAM answers the query protocol as XML, so the console reads it the way a client does.

/** The emulator's answer as a document, or null when the operation returns no body. */
export function parseIam(body) {
  if (!body) return null
  const doc = new DOMParser().parseFromString(body, 'application/xml')
  if (doc.getElementsByTagName('parsererror').length) return null
  return doc
}

/** The text of the first `tag` under `node`. */
export function text(node, tag) {
  if (!node) return ''
  const found = node.getElementsByTagName(tag)[0]
  return found ? found.textContent || '' : ''
}

/** Every `<member>` directly inside `container`, in document order. */
export function members(node, container) {
  if (!node) return []
  const box = node.getElementsByTagName(container)[0]
  if (!box) return []
  return [...box.children].filter((child) => child.tagName === 'member')
}

/** The `tag` inside each member of `container`. */
export function column(node, container, tag) {
  return members(node, container)
    .map((member) => text(member, tag))
    .filter(Boolean)
}

/** The text of each member itself, for lists like `<PolicyNames><member>read</member>`. */
export function values(node, container) {
  return members(node, container)
    .map((member) => (member.textContent || '').trim())
    .filter(Boolean)
}

/** GetAccountSummary's `<SummaryMap><entry><key>…</key><value>…</value></entry>`. */
export function summary(node) {
  const map = {}
  for (const entry of node?.getElementsByTagName('entry') || []) {
    const key = text(entry, 'key')
    if (key) map[key] = text(entry, 'value')
  }
  return map
}

/** A policy document arrives URL-encoded inside the XML; show it as written. */
export function documentText(value) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value || ''
  }
}
