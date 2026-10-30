import { ref, computed, readonly } from 'vue'

// ── Types ──────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  display_name: string | null
  created_at: string
  is_admin: boolean
}

export interface AuthState {
  token: string | null
  user: User | null
}

// ── Storage ────────────────────────────────────────────────────────

const TOKEN_KEY = 'channelzero-jwt'
const USER_KEY = 'channelzero-user'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Module-level singleton state ───────────────────────────────────

const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
const user = ref<User | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// Hydrate user from localStorage
try {
  const stored = localStorage.getItem(USER_KEY)
  if (stored) user.value = JSON.parse(stored)
} catch { /* ignore */ }

// ── Derived ────────────────────────────────────────────────────────

const isAuthenticated = computed(() => !!token.value)

// ── Helpers ────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  if (!token.value) return {}
  return { Authorization: `Bearer ${token.value}` }
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(opts.headers || {}),
    },
  })
  // 401 on auth endpoints means bad credentials, not an expired session —
  // let it fall through to the normal error path below
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    logout()
    window.location.href = '/login'
    throw new Error('Session expired')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    // Connectors answer {detail: {code, message}}; older routes, a string.
    const d = body.detail
    const msg = d && typeof d === 'object' ? (d.message || d.code) : d
    throw new Error(msg || `Request failed: ${res.status}`)
  }
  return res.json()
}

// ── Actions ────────────────────────────────────────────────────────

async function register(email: string, password: string, displayName?: string) {
  loading.value = true
  error.value = null
  try {
    const data = await apiFetch<{ access_token: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name: displayName || null }),
    })
    token.value = data.access_token
    localStorage.setItem(TOKEN_KEY, data.access_token)
    await fetchMe()
  } catch (e: any) {
    error.value = e.message
    throw e
  } finally {
    loading.value = false
  }
}

async function login(email: string, password: string) {
  loading.value = true
  error.value = null
  try {
    const data = await apiFetch<{ access_token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    token.value = data.access_token
    localStorage.setItem(TOKEN_KEY, data.access_token)
    await fetchMe()
  } catch (e: any) {
    error.value = e.message
    throw e
  } finally {
    loading.value = false
  }
}

async function fetchMe() {
  if (!token.value) return
  try {
    const data = await apiFetch<User>('/api/auth/me')
    user.value = data
    localStorage.setItem(USER_KEY, JSON.stringify(data))
  } catch {
    // Token expired or invalid — clear state
    logout()
  }
}

async function loginWithProvider(provider: 'google' | 'x', code: string, codeVerifier?: string) {
  loading.value = true
  error.value = null
  try {
    const body: Record<string, string> = { code }
    if (codeVerifier) body.code_verifier = codeVerifier
    const data = await apiFetch<{ access_token: string; user: User }>(
      `/api/auth/${provider}`,
      { method: 'POST', body: JSON.stringify(body) },
    )
    token.value = data.access_token
    localStorage.setItem(TOKEN_KEY, data.access_token)
    user.value = data.user
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  } catch (e: any) {
    error.value = e.message
    throw e
  } finally {
    loading.value = false
  }
}

function logout() {
  token.value = null
  user.value = null
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// ── Export ──────────────────────────────────────────────────────────

export function useAuthStore() {
  return {
    token: readonly(token),
    user: readonly(user),
    loading: readonly(loading),
    error: readonly(error),
    isAuthenticated,

    register,
    login,
    loginWithProvider,
    logout,
    fetchMe,

    // Expose for other composables that need authenticated fetch
    authHeaders,
    apiFetch,
  }
}
