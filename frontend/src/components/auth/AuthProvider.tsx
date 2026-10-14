import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi, privacyApi, type AuthUser, type SessionPayload } from '../../lib/api/auth'
import { isUnreachableError, setConsentRequiredHandler, setCsrfToken, setUnauthorizedHandler } from '../../lib/api/client'
import { setStoreUser } from '../../lib/analysis/store'
import { AuthContext, type AuthState, type AuthStatus } from '../../lib/auth/context'
import { setBattleUser } from '../../lib/battles'
import { getConsent, needsChoice, onConsentChanged } from '../../lib/consent'

const unreachable = isUnreachableError

const HAS_SESSION_KEY = 'sa_has_session'

function hasSessionHint(): boolean {
  try {
    return localStorage.getItem(HAS_SESSION_KEY) === '1'
  } catch {
    return false
  }
}

/** Owns the signed-in user. The session cookie is HttpOnly; only the CSRF token lives here, in memory. */
export default function AuthProvider({ children }: { children: ReactNode }) {
  // If there is no previous session stored, start immediately in 'signedOut' state
  // to eliminate the white splash screen and redirect to login instantly without waiting.
  const [status, setStatus] = useState<AuthStatus>(() => (hasSessionHint() ? 'loading' : 'signedOut'))
  const [user, setUser] = useState<AuthUser | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [consentNeeded, setConsentNeeded] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)

  const apply = useCallback((p: SessionPayload | null, why: string | null = null) => {
    setCsrfToken(p?.csrf_token ?? null)
    setStoreUser(p?.user.id ?? null)
    setBattleUser(p?.user.id ?? null)
    setUser(p?.user ?? null)
    setSessionId(p?.session_id ?? null)
    setConsentNeeded(p?.consent_needed ?? [])
    setStatus(p ? 'signedIn' : 'signedOut')
    try {
      if (p) {
        localStorage.setItem(HAS_SESSION_KEY, '1')
      } else {
        localStorage.removeItem(HAS_SESSION_KEY)
      }
    } catch {
      /* ignore storage errors */
    }
    if (why !== null) setNotice(why)
  }, [])

  /** Keep a server-side record of the storage choice (accountability), when signed in. */
  const recordCookieChoice = useCallback(() => {
    if (needsChoice()) return
    const c = getConsent()
    privacyApi.recordCookieChoice(c.preferences, c.history).catch(() => {
      /* best effort: the choice itself is already applied in this browser */
    })
  }, [])

  const refresh = useCallback(async () => {
    try {
      apply(await authApi.me())
    } catch (e) {
      if (unreachable(e)) {
        setStatus(hasSessionHint() ? 'offline' : 'signedOut')
      } else {
        apply(null)
      }
    }
  }, [apply])

  // Initial session check on page load.
  useEffect(() => {
    let alive = true
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0

    const checkSession = () => {
      authApi
        .me()
        .then((p) => {
          if (!alive) return
          apply(p)
        })
        .catch((e) => {
          if (!alive) return
          if (!unreachable(e)) {
            apply(null)
            return
          }
          // In local development the launcher starts Vite and Uvicorn concurrently,
          // so allow brief retry. In production, only retry if a known session was stored.
          const shouldRetry = (import.meta.env.DEV || hasSessionHint()) && attempt < 2
          if (shouldRetry) {
            attempt += 1
            retryTimer = setTimeout(checkSession, 1000)
          } else {
            if (hasSessionHint()) {
              setStatus('offline')
            } else {
              apply(null)
            }
          }
        })
    }

    checkSession()
    return () => {
      alive = false
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [apply])

  // Automatically poll every 3 seconds to recover as soon as the server wakes up / deploys
  useEffect(() => {
    if (status !== 'offline') return
    const pollTimer = setInterval(() => {
      void refresh()
    }, 3000)
    return () => clearInterval(pollTimer)
  }, [status, refresh])

  // Any API call that comes back 401 means the session ended elsewhere;
  // CONSENT_REQUIRED means updated terms were published while the page was open.
  useEffect(() => {
    setUnauthorizedHandler(() => apply(null, 'Your session ended. Sign in again to continue.'))
    setConsentRequiredHandler(() => void refresh())
    return () => {
      setUnauthorizedHandler(null)
      setConsentRequiredHandler(null)
    }
  }, [apply, refresh])

  // Record a changed storage choice while signed in.
  useEffect(() => {
    if (status !== 'signedIn') return
    return onConsentChanged(recordCookieChoice)
  }, [status, recordCookieChoice])

  const signIn = useCallback(
    async (email: string, password: string) => {
      apply(await authApi.login(email, password), null)
      setNotice(null)
      recordCookieChoice()
    },
    [apply, recordCookieChoice],
  )

  const register = useCallback(
    async (email: string, displayName: string, password: string) => {
      apply(await authApi.register(email, displayName, password), null)
      setNotice(null)
      recordCookieChoice()
    },
    [apply, recordCookieChoice],
  )

  const signOut = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      /* the session may already be gone; sign out locally regardless */
    }
    apply(null, 'You signed out.')
  }, [apply])

  const acceptDocuments = useCallback(async (docs: string[]) => {
    const r = await privacyApi.accept(docs)
    setConsentNeeded(r.outstanding)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      sessionId,
      consentNeeded,
      notice,
      signIn,
      register,
      signOut,
      accountDeleted: () => apply(null, 'Your account and its data were deleted.'),
      acceptDocuments,
      refresh,
      updateUser: setUser,
      clearNotice: () => setNotice(null),
    }),
    [status, user, sessionId, consentNeeded, notice, signIn, register, signOut, apply, acceptDocuments, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
