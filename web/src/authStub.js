// Where the sign-in screens submit until the control plane exposes the auth
// endpoints described in ARCHITECTURE.md (slice 3).
//
// Nothing here touches the network and no session is minted: the stub waits and
// returns the principal the console would have signed in as, plus whether that
// principal has MFA enabled. The payloads are the ones the endpoints will take,
// so wiring the real thing is a swap of this module for `api` — the page never
// learns that it is talking to a stub.
//
// Passwords are deliberately *not* part of the payload: a stub has nothing to
// check them against, and this way no credential ever reaches module state.

export const STUB_LATENCY_MS = 200

const wait = () => new Promise((resolve) => setTimeout(resolve, STUB_LATENCY_MS))

// `?mfa=1` on /signin: the third screen only exists for principals that have MFA
// enabled, and the stub cannot know that, so the preview asks for it explicitly.
// The real endpoint reads the flag off the principal and this option goes away.
const MFA_PREVIEW_PARAM = 'mfa'

export const mfaPreviewRequested = (params) =>
  params.get(MFA_PREVIEW_PARAM) === '1'

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const ALIAS = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/

// '' when the reference is usable, otherwise the sentence the field shows.
export function emailProblem(value) {
  return EMAIL.test(value.trim()) ? '' : 'That email address does not look right.'
}

export function accountProblem(value) {
  const reference = value.trim()
  if (/^\d+$/.test(reference)) {
    return reference.length === 12 ? '' : 'An account ID is exactly 12 digits.'
  }
  return ALIAS.test(reference.toLowerCase())
    ? ''
    : 'Use the 12-digit account ID or the account alias.'
}

export async function signIn({ userType, email = '', account = '', username = '', mfa = false }) {
  await wait()
  // The real endpoint answers this from the principal's record. The stub has no
  // record to read, so MFA is off unless the page asks for it (?mfa=1) — an
  // account without MFA enabled must never be shown the code screen.
  return {
    mfaRequired: Boolean(mfa),
    principal: {
      type: userType === 'root' ? 'ROOT' : 'IAM_USER',
      email,
      account,
      username,
    },
  }
}

export async function verifyMfa({ code }) {
  await wait()
  return { signedIn: Boolean(code) }
}
