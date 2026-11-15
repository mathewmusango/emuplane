import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'

import { useLocation } from 'react-router-dom'

const SessionContext = createContext(null)
const REGION_KEY = 'emuplane:region'
const ACCOUNT_KEY = 'emuplane:account'

// Routes that exist without a session. `/api/meta` can only answer 401 there, so
// the console must not ask for it — and a fresh sign-in then loads it on the way
// into the app, which is what makes the data current.
const SIGNED_OUT_ROUTES = ['/login', '/signin', '/forgot', '/reset']

export const useSession = () => useContext(SessionContext)

export function SessionProvider({ children }) {
  const location = useLocation()
  const signedOut = SIGNED_OUT_ROUTES.includes(location.pathname)
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [region, setRegionState] = useState(
    () => sessionStorage.getItem(REGION_KEY) || 'us-east-1',
  )
  const [account, setAccountState] = useState(
    () => sessionStorage.getItem(ACCOUNT_KEY) || '',
  )

  const refresh = useCallback(async () => {
    try {
      const next = await api.meta()
      setMeta(next)
      setError('')
      setAccountState((current) => {
        const known = next.accounts.some((item) => item.account_id === current)
        const chosen = known
          ? current
          : next.me?.account || next.accounts[0]?.account_id || ''
        sessionStorage.setItem(ACCOUNT_KEY, chosen)
        return chosen
      })
      setRegionState((current) => {
        // Selectable regions are the ones the account enabled; a node is not
        // required (the emulator serves every region).
        const enabled = next.regions?.length ? next.regions : ['us-east-1']
        const chosen = enabled.includes(current) ? current : enabled[0]
        sessionStorage.setItem(REGION_KEY, chosen)
        return chosen
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (signedOut) {
      setLoading(false)
      return
    }
    refresh()
  }, [signedOut, location.pathname, refresh])

  const setRegion = useCallback((next) => {
    setRegionState(next)
    sessionStorage.setItem(REGION_KEY, next)
  }, [])

  const setAccount = useCallback((next) => {
    setAccountState(next)
    sessionStorage.setItem(ACCOUNT_KEY, next)
  }, [])

  const value = useMemo(
    () => ({
      meta,
      me: meta?.me,
      error,
      loading,
      refresh,
      region,
      setRegion,
      account,
      setAccount,
    }),
    [meta, error, loading, refresh, region, account, setRegion, setAccount],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
