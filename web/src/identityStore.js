// Identities this browser can switch between.
//
// Off by default. When the account menu's "Turn on multi-session support" is
// enabled, a successful sign-in also stores that session's token here, so the
// menu can switch back to it without asking for the password again.
//
// This is the one place where a session token sits in `localStorage`, which is
// readable by any script on the page — the reason it is opt-in and never the
// default. Turning the feature off drops every stored token.

const ENABLED_KEY = 'emuplane:multi-session'
const IDENTITIES_KEY = 'emuplane:identities'

export const multiSessionEnabled = () => {
  try {
    return localStorage.getItem(ENABLED_KEY) === 'on'
  } catch {
    return false
  }
}

export const enableMultiSession = (enabled) => {
  try {
    if (enabled) {
      localStorage.setItem(ENABLED_KEY, 'on')
    } else {
      localStorage.removeItem(ENABLED_KEY)
      localStorage.removeItem(IDENTITIES_KEY)
    }
  } catch {
    // storage denied: the feature stays off for this session
  }
}

export const readIdentities = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(IDENTITIES_KEY) || '[]')
    return Array.isArray(raw) ? raw.filter((item) => item && item.token) : []
  } catch {
    return []
  }
}

const write = (list) => {
  try {
    localStorage.setItem(IDENTITIES_KEY, JSON.stringify(list))
  } catch {
    // storage denied: switching works only within this page's lifetime
  }
}

/** Remember one identity, replacing any earlier entry for the same user. */
export const remember = ({ token, user, alias, account, role }) => {
  if (!multiSessionEnabled() || !token) return
  const others = readIdentities().filter((item) => item.user !== user || item.account !== account)
  write([{ token, user, alias, account, role }, ...others].slice(0, 8))
}

export const forget = (token) => {
  write(readIdentities().filter((item) => item.token !== token))
}

/** Drop an identity by who it is, for when the token is not to hand. */
export const forgetIdentity = (user, account) => {
  write(readIdentities().filter((item) => item.user !== user || item.account !== account))
}
