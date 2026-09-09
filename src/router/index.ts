import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // ── Auth ─────────────────────────────────────────────────────
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true }
    },

    // ── Hub ──────────────────────────────────────────────────────
    {
      path: '/',
      name: 'home',
      component: HomeView
    },

    // ── Primary nav: Learn / Sessions / About ───────────────────
    {
      path: '/learn',
      name: 'learn',
      component: () => import('@/views/LearnIndexView.vue')
    },
    {
      path: '/learn/:slug',
      name: 'learn-article',
      component: () => import('@/views/LearnArticleView.vue')
    },
    {
      path: '/sessions',
      name: 'sessions',
      component: () => import('@/views/SessionsView.vue')
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('@/views/AboutView.vue')
    },

    // ── Experiences (existing) ───────────────────────────────────
    {
      path: '/reader',
      name: 'reader',
      component: () => import('@/views/ReaderView.vue')
    },
    {
      path: '/zeromind',
      name: 'zeromind',
      component: () => import('@/views/ZeromindView.vue')
    },
    {
      path: '/studio',
      name: 'studio',
      component: () => import('@/views/GlassView.vue')
    },
    {
      path: '/liquidglass',
      name: 'liquidglass',
      component: () => import('@/views/LiquidGlassView.vue')
    },
    {
      path: '/audio',
      name: 'audio',
      component: () => import('@/views/AudioplayerView.vue')
    },
    {
      path: '/spiral',
      name: 'spiral',
      component: () => import('@/views/SpiralView.vue')
    },
    {
      path: '/trance',
      name: 'trance',
      component: () => import('@/views/TranceView.vue')
    },
    {
      path: '/hypno',
      name: 'hypno',
      component: () => import('@/views/HypnoView.vue')
    },
    {
      path: '/poll',
      name: 'poll',
      component: () => import('@/views/PollView.vue')
    },
    {
      path: '/fitting',
      name: 'fitting',
      component: () => import('@/views/Fitting.vue')
    },
    {
      path: '/webaudio',
      name: 'webaudio',
      component: () => import('@/views/WebAudioView.vue')
    },

    // ── Journal + Check-in (auth required) ──────────────────────
    {
      path: '/journal',
      name: 'journal',
      component: () => import('@/views/JournalView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/checkin',
      name: 'checkin',
      component: () => import('@/views/CheckInView.vue'),
      meta: { requiresAuth: true }
    },

    // ── OAuth callback routes ────────────────────────────────────
    {
      path: '/auth/google/callback',
      name: 'google-callback',
      component: () => import('@/views/GoogleCallback.vue')
    },
    {
      path: '/auth/x/callback',
      name: 'x-callback',
      component: () => import('@/views/XCallback.vue')
    },
    {
      path: '/auth/strava/callback',
      name: 'strava-callback',
      component: () => import('@/views/StravaCallback.vue')
    },
    {
      path: '/auth/github/callback',
      name: 'github-callback',
      component: () => import('@/views/GitHubCallback.vue')
    },
    {
      path: '/auth/youtube/callback',
      name: 'youtube-callback',
      component: () => import('@/views/YouTubeCallback.vue')
    },
    {
      path: '/auth/reddit/callback',
      name: 'reddit-callback',
      component: () => import('@/views/RedditCallback.vue')
    },
    {
      path: '/auth/instagram/callback',
      name: 'instagram-callback',
      component: () => import('@/views/InstagramCallback.vue')
    },
    {
      path: '/auth/tiktok/callback',
      name: 'tiktok-callback',
      component: () => import('@/views/TikTokCallback.vue')
    },

    // ── Vibe calibration (OAuth connections) ────────────────────
    {
      path: '/calibrate',
      name: 'calibrate',
      component: () => import('@/views/OauthView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/calibrate/:provider',
      name: 'connector-result',
      component: () => import('@/views/ConnectorResultView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Peripheral → calibrate redirect ──────────────────────────
    {
      path: '/peripheral',
      redirect: '/calibrate',
    },

    // ── Psychometrics / Psychoanalysis (auth required) ───────────
    {
      path: '/psychoanalysis',
      name: 'psychoanalysis',
      component: () => import('@/views/PsychoanalysisView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Integrated Portrait: cross-connector narrative ───────────
    {
      path: '/portrait',
      name: 'portrait',
      component: () => import('@/views/PortraitView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Onboarding (auth required) ───────────────────────────────
    {
      path: '/onboarding',
      name: 'onboarding',
      component: () => import('@/views/OnboardingView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Universe: solar system visualization (post-registration) ───
    {
      path: '/universe',
      name: 'universe',
      component: () => import('@/views/UniverseView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Discovery: physics-driven onboarding flow ─────────────────
    {
      path: '/discovery',
      name: 'discovery',
      component: () => import('@/views/DiscoveryView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Intake → Game pipeline (auth required) ──────────────────
    {
      path: '/intake',
      name: 'intake',
      component: () => import('@/views/IntakeView.vue'),
      meta: { requiresAuth: true }
    },
    // ── Spotify field visualization ──────────────────────────────────────
    {
      path: '/spotify',
      name: 'spotify',
      component: () => import('@/views/SpotifyView.vue'),
      meta: { requiresAuth: true }
    },

    // ── X/Twitter signal + imprint ───────────────────────────────────────
    {
      path: '/x',
      name: 'x',
      component: () => import('@/views/XView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Strava somatic ledger ──────────────────────────────────────────────
    {
      path: '/strava',
      name: 'strava',
      component: () => import('@/views/StravaView.vue'),
      meta: { requiresAuth: true }
    },

    // ── Admin analytics dashboard ────────────────────────────────────────
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

// ── Auth guard ──────────────────────────────────────────────────────
router.beforeEach((to) => {
  const token = localStorage.getItem('channelzero-jwt')

  // Redirect authenticated users away from guest-only pages
  if (to.meta.guest && token) {
    // If onboarding isn't done, send to onboarding instead of home
    const ob = localStorage.getItem('channelzero-onboarding')
    const onboarded = ob ? JSON.parse(ob).completed : false
    return { name: onboarded ? 'home' : 'discovery' }
  }

  // Redirect unauthenticated users to login for protected pages
  if (to.meta.requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router
