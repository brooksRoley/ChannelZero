<template>
  <div class="connector-panel">
    <div class="cp-header">
      <span class="cp-title">Signal Sources</span>
      <span class="cp-count" :class="connectedCount === connectors.length ? 'cp-count--full' : ''">
        {{ connectedCount }}<span class="cp-count-denom"> / {{ connectors.length }}</span>
      </span>
    </div>

    <div class="cp-bar">
      <div
        class="cp-bar-fill"
        :style="{ width: `${(connectedCount / connectors.length) * 100}%` }"
      ></div>
    </div>

    <div class="cp-pills">
      <button
        v-for="c in connectors"
        :key="c.key"
        class="cp-pill"
        :class="{
          'cp-pill--on': c.connected,
          'cp-pill--loading': c.key === loadingKey,
        }"
        :title="c.connected ? `${c.label} — view your signal` : `Connect ${c.label}`"
        @click="handleConnect(c)"
      >
        <span class="cp-pill-dot" :class="c.connected ? 'dot--on' : 'dot--off'"></span>
        <span class="cp-pill-icon" v-html="c.svg"></span>
        <span class="cp-pill-label">{{ c.label }}</span>
        <span v-if="c.key === loadingKey" class="cp-spinner"></span>
      </button>
    </div>

    <router-link to="/calibrate" class="cp-manage">
      Manage sources
      <svg class="cp-manage-arrow" viewBox="0 0 16 16" fill="none">
        <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5"
              stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'
import { useVibeStore } from '@/composables/useVibeStore'

const router = useRouter()
const { token, logout } = useAuthStore()
const { oauthState } = useVibeStore()

const API = import.meta.env.VITE_API_URL || ''
const loadingKey = ref<string | null>(null)

// ── Connector definitions ────────────────────────────────────────

const connectors = computed(() => [
  {
    key: 'spotify',
    label: 'Spotify',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#1DB954" d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const ctResp = await fetch(`${API}/api/auth/connect-token`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (ctResp.status === 401) { logout(); window.location.href = '/login'; return }
      const { ct } = await ctResp.json()
      window.location.href = `${API}/api/spotify/connect?ct=${ct}`
    },
    connected: oauthState.value.spotify.connected,
  },
  {
    key: 'twitter',
    label: 'X',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/twitter/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.twitter.connected,
  },
  {
    key: 'google',
    label: 'Calendar',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.6 12.23c0-.82-.07-1.61-.2-2.37H12v4.48h5.38c-.23 1.15-.86 2.12-1.73 2.76v2.3h2.8c1.64-1.51 2.58-3.74 2.58-6.17z"/><path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.42l-2.8-2.3c-.9.6-2.06.95-3.82.95-2.93 0-5.4-1.98-6.28-4.65H2.8v2.37C4.46 19.22 7.96 22 12 22z"/><path fill="#FBBC05" d="M5.72 13.58c-.23-.68-.36-1.4-.36-2.14s.13-1.46.36-2.14V6.93H2.8C2.26 8 2 9.17 2 10.42c0 1.25.26 2.42.8 3.5l2.92-2.34z"/><path fill="#EA4335" d="M12 5.05c1.47 0 2.78.5 3.82 1.49l2.86-2.86C16.96 2.04 14.7 1 12 1 7.96 1 4.46 3.78 2.8 6.93l2.92 2.34c.88-2.67 3.35-4.65 6.28-4.65z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const ctResp = await fetch(`${API}/api/auth/connect-token`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (ctResp.status === 401) { logout(); window.location.href = '/login'; return }
      const { ct } = await ctResp.json()
      window.location.href = `${API}/api/gcal/connect?ct=${ct}`
    },
    connected: oauthState.value.google.connected,
  },
  {
    key: 'costar',
    label: 'Co-Star',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="2" fill="currentColor"/><path fill="currentColor" d="M12 2l1.5 4.5L18 4l-2.5 4.5L20 12l-4.5 1.5L18 18l-4.5-2.5L12 20l-1.5-4.5L6 18l2.5-4.5L4 12l4.5-1.5L6 6l4.5 2.5z" opacity=".7"/></svg>`,
    connect: () => router.push('/calibrate'),
    connected: oauthState.value.costar.connected,
  },
  {
    key: 'letterboxd',
    label: 'Letterboxd',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="12" r="5" fill="#00C030" opacity=".9"/><circle cx="16" cy="12" r="5" fill="#FF8000" opacity=".85"/><ellipse cx="12" cy="12" rx="2.5" ry="5" fill="#FFCC00" opacity=".9"/></svg>`,
    connect: () => router.push('/calibrate'),
    connected: oauthState.value.letterboxd.connected,
  },
  {
    key: 'steam',
    label: 'Steam',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#1b2838" d="M0 12C0 5.37 5.37 0 12 0s12 5.37 12 12-5.37 12-12 12A12 12 0 010 12z"/><path fill="#c6d4df" d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.49l2.45-5.09A3.5 3.5 0 0112 9.5a3.5 3.5 0 013.5 3.5A3.5 3.5 0 0112 16.5c-.23 0-.46-.02-.68-.06l-3.03 3.18A10 10 0 0022 12c0-5.52-4.48-10-10-10z"/><circle cx="12" cy="13" r="2.5" fill="#1b2838"/></svg>`,
    connect: () => router.push('/calibrate'),
    connected: oauthState.value.steam.connected,
  },
  {
    key: 'github',
    label: 'GitHub',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/github/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.github.connected,
  },
  {
    key: 'youtube',
    label: 'YouTube',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#FF0000" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/youtube/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.youtube.connected,
  },
  {
    key: 'reddit',
    label: 'Reddit',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="12" fill="#FF4500"/><path fill="#fff" d="M19.6 12.4c0-.8-.6-1.4-1.4-1.4-.4 0-.7.1-1 .4-1-.7-2.3-1.1-3.8-1.2l.6-3 2.1.5c0 .6.5 1.1 1.1 1.1.6 0 1.1-.5 1.1-1.1s-.5-1.1-1.1-1.1c-.5 0-.9.3-1 .7l-2.4-.5c-.1 0-.2 0-.2.1l-.7 3.3c-1.5.1-2.9.5-3.9 1.2-.3-.3-.6-.4-1-.4-.8 0-1.4.6-1.4 1.4 0 .5.3 1 .7 1.2v.4c0 2.1 2.5 3.9 5.5 3.9s5.5-1.7 5.5-3.9v-.4c.4-.3.7-.7.7-1.2zm-9.8 1.1c0-.6.5-1.1 1.1-1.1.6 0 1.1.5 1.1 1.1 0 .6-.5 1.1-1.1 1.1-.6 0-1.1-.5-1.1-1.1zm6.2 2.6c-.8.8-2 .8-2 .8s-1.2 0-2-.8c-.1-.1 0-.2.1-.2.1-.1.2 0 .2.1.6.6 1.7.6 1.7.6s1.1 0 1.7-.6c.1-.1.2-.1.2 0 .2 0 .2.1.1.1zm-.2-1.5c-.6 0-1.1-.5-1.1-1.1 0-.6.5-1.1 1.1-1.1.6 0 1.1.5 1.1 1.1 0 .6-.5 1.1-1.1 1.1z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/reddit/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.reddit.connected,
  },
  {
    key: 'instagram',
    label: 'Instagram',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="ig" x1="0" y1="1" x2="1" y2="0"><stop offset="0%" stop-color="#feda75"/><stop offset="25%" stop-color="#fa7e1e"/><stop offset="50%" stop-color="#d62976"/><stop offset="75%" stop-color="#962fbf"/><stop offset="100%" stop-color="#4f5bd5"/></linearGradient></defs><rect width="20" height="20" x="2" y="2" rx="5" fill="none" stroke="url(#ig)" stroke-width="2"/><circle cx="12" cy="12" r="4.5" fill="none" stroke="url(#ig)" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.2" fill="url(#ig)"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/instagram/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.instagram.connected,
  },
  {
    key: 'tiktok',
    label: 'TikTok',
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1v-3.52a6.37 6.37 0 0 0-.79-.05A6.34 6.34 0 0 0 3.15 15.2a6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V9.39a8.16 8.16 0 0 0 4.76 1.53V7.39a4.85 4.85 0 0 1-1-.7z"/></svg>`,
    connect: async () => {
      if (!token.value) return
      const res = await fetch(`${API}/api/tiktok/connect`, {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (res.status === 401) { logout(); window.location.href = '/login'; return }
      const data = await res.json()
      if (data.auth_url) window.location.href = data.auth_url
    },
    connected: oauthState.value.tiktok.connected,
  },
])

const connectedCount = computed(() => connectors.value.filter((c) => c.connected).length)

// ── Connect handler ──────────────────────────────────────────────

// Steam has no connector config page yet — its connected pill goes to /calibrate
const inspectablePages = new Set([
  'spotify', 'twitter', 'google', 'github', 'youtube',
  'reddit', 'letterboxd', 'instagram', 'tiktok', 'costar',
])

async function handleConnect(c: { connected: boolean; key: string; connect: () => Promise<void> | void }) {
  if (c.connected) {
    router.push(inspectablePages.has(c.key) ? `/calibrate/${c.key}` : '/calibrate')
    return
  }
  if (loadingKey.value) return
  loadingKey.value = c.key as string
  try {
    await c.connect()
  } finally {
    // Only clear if still on this page (redirects won't reach here)
    loadingKey.value = null
  }
}
</script>

<style scoped>
.connector-panel {
  margin: 1.25rem 0;
  padding: 1rem 1.25rem;
  background: rgba(15, 15, 30, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 0.75rem;
  backdrop-filter: blur(10px);
}

/* ── Header ── */
.cp-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.6rem;
}

.cp-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #475569;
  font-weight: 600;
}

.cp-count {
  font-size: 0.8rem;
  font-weight: 700;
  color: #6366f1;
  font-variant-numeric: tabular-nums;
  transition: color 0.3s;
}

.cp-count--full {
  color: #22c55e;
}

.cp-count-denom {
  font-weight: 400;
  color: #334155;
}

/* ── Progress bar ── */
.cp-bar {
  height: 2px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 1px;
  overflow: hidden;
  margin-bottom: 0.9rem;
}

.cp-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #22c55e);
  border-radius: 1px;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Pills ── */
.cp-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.9rem;
}

.cp-pill {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.7rem 0.35rem 0.5rem;
  border-radius: 100px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  font-family: inherit;
  font-size: 0.72rem;
  color: #64748b;
  transition: border-color 0.2s, background 0.2s, color 0.2s, box-shadow 0.2s;
  position: relative;
  overflow: hidden;
}

.cp-pill:hover:not(.cp-pill--on) {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.08);
  color: #94a3b8;
}

.cp-pill--on {
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.06);
  color: #86efac;
}

.cp-pill--on:hover {
  border-color: rgba(34, 197, 94, 0.6);
  background: rgba(34, 197, 94, 0.12);
}

.cp-pill--loading {
  opacity: 0.7;
  cursor: wait;
}

/* Status dot */
.cp-pill-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot--on {
  background: #22c55e;
  box-shadow: 0 0 4px rgba(34, 197, 94, 0.7);
}

.dot--off {
  background: #334155;
}

/* Icon */
.cp-pill-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cp-pill-icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.cp-pill-label {
  font-weight: 500;
  white-space: nowrap;
}

/* Spinner */
.cp-spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(99, 102, 241, 0.3);
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: cp-spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes cp-spin {
  to { transform: rotate(360deg); }
}

/* ── Manage link ── */
.cp-manage {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.68rem;
  color: #475569;
  text-decoration: none;
  transition: color 0.15s;
}

.cp-manage:hover {
  color: #818cf8;
}

.cp-manage-arrow {
  width: 12px;
  height: 12px;
}
</style>
