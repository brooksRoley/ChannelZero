<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as Tone from 'tone'
import { useStoryStore } from '@/composables/useStoryStore'
import { useTranceEngine } from '@/composables/useTranceEngine'
import { useAnalytics } from '@/composables/useAnalytics'
import PostTranceOverlay from '@/components/PostTranceOverlay.vue'

const { currentWord } = useStoryStore()
const { logEvent } = useAnalytics()
const {
  phase,
  sessionActive,
  currentInstruction,
  phaseAccent,
  phaseDisplayName,
  completedSession,
  clearCompletedSession,
} = useTranceEngine()

const showOverlay = ref(false)

watch(completedSession, (data) => {
  if (data) {
    showOverlay.value = true
    logEvent('zeromind_session_completed', {
      coherence: data.coherence,
      sync_count: data.syncCount,
      duration_ms: data.sessionDurationMs,
    })
  }
})

function handleOverlayClose() {
  showOverlay.value = false
  clearCompletedSession()
}
const canvas = ref<HTMLCanvasElement>()

// ── Audio config per mode ─────────────────────────────────────────
interface AudioModeCfg {
  bpm: number
  note: string
  filterHz: number
  beatEvery: number   // fire kick every N beats (1 = every beat)
  droneMod: number    // FM modulationIndex
  reverbWet: number   // 0–1
  droneVol: number    // dB
  bellVol: number     // dB — -99 = silent
  noiseVol: number    // dB
  bellArp: string[] | null  // null = single hit, array = ascending arp (glow)
}

const AUDIO_MODES: Record<string, AudioModeCfg> = {
  void:    { bpm: 28,  note: 'A1', filterHz: 180, beatEvery: 4, droneMod: 1.5, reverbWet: 0.65, droneVol: -20, bellVol: -99, noiseVol: -30, bellArp: null },
  flux:    { bpm: 62,  note: 'D2', filterHz: 420, beatEvery: 1, droneMod: 3,   reverbWet: 0.4,  droneVol: -18, bellVol: -99, noiseVol: -28, bellArp: null },
  cascade: { bpm: 90,  note: 'F2', filterHz: 660, beatEvery: 1, droneMod: 5,   reverbWet: 0.25, droneVol: -16, bellVol: -99, noiseVol: -26, bellArp: null },
  pulse:   { bpm: 76,  note: 'C2', filterHz: 360, beatEvery: 1, droneMod: 4,   reverbWet: 0.35, droneVol: -18, bellVol: -99, noiseVol: -27, bellArp: null },
  zen:     { bpm: 22,  note: 'E2', filterHz: 150, beatEvery: 4, droneMod: 1,   reverbWet: 0.72, droneVol: -22, bellVol: -18, noiseVol: -32, bellArp: null },
  settle:  { bpm: 40,  note: 'B1', filterHz: 240, beatEvery: 2, droneMod: 2,   reverbWet: 0.58, droneVol: -20, bellVol: -24, noiseVol: -30, bellArp: null },
  descent: { bpm: 35,  note: 'G1', filterHz: 165, beatEvery: 2, droneMod: 1.2, reverbWet: 0.62, droneVol: -19, bellVol: -26, noiseVol: -29, bellArp: null },
  glow:    { bpm: 68,  note: 'A2', filterHz: 520, beatEvery: 1, droneMod: 3.5, reverbWet: 0.45, droneVol: -17, bellVol: -20, noiseVol: -27, bellArp: ['A3','C4','E4','G4','A4','C5'] },
}

// ── Audio state ───────────────────────────────────────────────────
const T = Tone as any
let audioReady = false
let masterGain: any = null
let reverb: any = null
let droneOsc: any = null
let kickSynth: any = null
let bellSynth: any = null
let noiseSrc: any = null
let noiseFilt: any = null
let breathLfo: any = null
let beatTimer: ReturnType<typeof setInterval> | null = null
let beatCount = 0
let bellArpIdx = 0

async function startAudio() {
  if (audioReady) return
  try { await T.start() } catch { return }

  reverb = new T.Reverb({ decay: 6, wet: 0.45 })
  masterGain = new T.Gain(0.18).toDestination()
  reverb.connect(masterGain)

  droneOsc = new T.FMSynth({
    harmonicity: 2,
    modulationIndex: 3,
    oscillator: { type: 'sine' },
    envelope: { attack: 6, decay: 0, sustain: 1, release: 10 },
    modulation: { type: 'triangle' },
    modulationEnvelope: { attack: 4, decay: 0, sustain: 1, release: 10 },
    volume: -20,
  }).connect(reverb)

  kickSynth = new T.MembraneSynth({
    pitchDecay: 0.065,
    octaves: 8,
    envelope: { attack: 0.001, decay: 0.38, sustain: 0, release: 0.15 },
    volume: -14,
  }).connect(reverb)

  bellSynth = new T.PolySynth(T.Synth, {
    oscillator: { type: 'sine' },
    envelope: { attack: 0.005, decay: 3.2, sustain: 0, release: 2 },
    volume: -22,
  }).connect(reverb)

  noiseFilt = new T.Filter({ frequency: 240, type: 'lowpass', rolloff: -24 }).connect(reverb)
  noiseSrc = new T.Noise('pink').connect(noiseFilt)
  noiseSrc.volume.value = -30
  noiseSrc.start()

  breathLfo = new T.LFO({ frequency: 0.1, min: 0.14, max: 0.22 }).start()
  breathLfo.connect(masterGain.gain)

  const cfg = AUDIO_MODES[MODES[modeIndex.value].id] ?? AUDIO_MODES.flux
  droneOsc.triggerAttack(cfg.note)

  audioReady = true
  applyAudioMode(MODES[modeIndex.value].id, 0)
  restartBeat(MODES[modeIndex.value].id, cfg)
}

function applyAudioMode(modeId: string, ramp = 1.2) {
  if (!audioReady) return
  const cfg = AUDIO_MODES[modeId] ?? AUDIO_MODES.flux
  const now = T.now()
  const r = Math.max(ramp, 0.01)

  droneOsc.modulationIndex.rampTo(cfg.droneMod, r, now)
  droneOsc.volume.rampTo(cfg.droneVol, r, now)
  noiseFilt.frequency.rampTo(cfg.filterHz, r, now)
  noiseSrc.volume.rampTo(cfg.noiseVol, r, now)
  bellSynth.volume.rampTo(cfg.bellVol, r, now)
  reverb.wet.rampTo(cfg.reverbWet, r, now)
}

function restartBeat(modeId: string, cfg: AudioModeCfg) {
  if (beatTimer) clearInterval(beatTimer)
  beatCount = 0
  bellArpIdx = 0
  const intervalMs = Math.round(60000 / cfg.bpm)
  beatTimer = setInterval(() => {
    if (!audioReady) return
    beatCount++
    if (beatCount % cfg.beatEvery === 0) {
      try {
        kickSynth.triggerAttackRelease(cfg.note, '8n', T.now())
      } catch { /* noop */ }
    }
    // Bell/chime for modes that have them
    if (cfg.bellVol > -40) {
      const shouldBell = modeId === 'zen'
        ? beatCount % 4 === 0 && Math.random() < 0.55
        : modeId === 'settle' || modeId === 'descent'
          ? beatCount % 8 === 0
          : modeId === 'glow'
            ? beatCount % 2 === 0
            : false
      if (shouldBell) {
        try {
          if (cfg.bellArp && cfg.bellArp.length > 0) {
            const note = cfg.bellArp[bellArpIdx % cfg.bellArp.length]
            bellArpIdx++
            bellSynth.triggerAttackRelease(note, '4n', T.now())
          } else {
            // Single chime — random high note appropriate to mode
            const zChimes: Record<string, string[]> = {
              zen:     ['C6','E6','G6','B5'],
              settle:  ['B4','D5','F#5'],
              descent: ['G4','Bb4','D5'],
            }
            const pool = zChimes[modeId] ?? ['C5']
            bellSynth.triggerAttackRelease(pool[Math.floor(Math.random() * pool.length)], '4n', T.now())
          }
        } catch { /* noop */ }
      }
    }
  }, intervalMs)
}

function destroyAudio() {
  if (beatTimer) { clearInterval(beatTimer); beatTimer = null }
  if (!audioReady) return
  try {
    droneOsc?.triggerRelease()
    noiseSrc?.stop()
    breathLfo?.stop()
    ;[droneOsc, kickSynth, bellSynth, noiseSrc, noiseFilt, breathLfo, reverb, masterGain].forEach(n => {
      try { n?.dispose?.() } catch { /* noop */ }
    })
  } catch { /* noop */ }
  droneOsc = kickSynth = bellSynth = noiseSrc = noiseFilt = breathLfo = reverb = masterGain = null
  audioReady = false
}

// ── Modes ─────────────────────────────────────────────────────────
interface Mode {
  id: string
  label: string
  glyph: string
  count: number
  speed: number
  noiseScale: number
  noiseStrength: number
  colors: [string, string, string, string]
  fade: number
  sizeMin: number
  sizeMax: number
  gravity: number
}

const MODES: Mode[] = [
  {
    id: 'void',
    label: 'Void',
    glyph: '○',
    count: 70,
    speed: 0.5,
    noiseScale: 0.0014,
    noiseStrength: 0.9,
    colors: ['#4a2d8a', '#2d1a6e', '#7b4fd4', '#1a0d3d'],
    fade: 0.025,
    sizeMin: 1, sizeMax: 3,
    gravity: 0,
  },
  {
    id: 'flux',
    label: 'Flux',
    glyph: '≈',
    count: 240,
    speed: 1.3,
    noiseScale: 0.0018,
    noiseStrength: 1.5,
    colors: ['#00c4cc', '#0087a8', '#00e5ff', '#006080'],
    fade: 0.035,
    sizeMin: 0.8, sizeMax: 2.5,
    gravity: 0.012,
  },
  {
    id: 'cascade',
    label: 'Cascade',
    glyph: '↓',
    count: 380,
    speed: 1.9,
    noiseScale: 0.0022,
    noiseStrength: 0.7,
    colors: ['#f59e0b', '#d97706', '#fbbf24', '#92400e'],
    fade: 0.045,
    sizeMin: 0.7, sizeMax: 2,
    gravity: 0.09,
  },
  {
    id: 'pulse',
    label: 'Pulse',
    glyph: '◉',
    count: 200,
    speed: 1.6,
    noiseScale: 0.0026,
    noiseStrength: 2.2,
    colors: ['#ec4899', '#be185d', '#f472b6', '#9d174d'],
    fade: 0.04,
    sizeMin: 1.5, sizeMax: 4.5,
    gravity: -0.018,
  },
  {
    id: 'zen',
    label: 'Zen',
    glyph: '✦',
    count: 45,
    speed: 0.35,
    noiseScale: 0.0009,
    noiseStrength: 0.55,
    colors: ['#e2e8f0', '#94a3b8', '#f8fafc', '#64748b'],
    fade: 0.018,
    sizeMin: 1, sizeMax: 4,
    gravity: 0,
  },
  // ── Trance-phase modes ───────────────────────────────────────────
  {
    id: 'settle',
    label: 'Settle',
    glyph: '∿',
    count: 90,
    speed: 0.45,
    noiseScale: 0.001,
    noiseStrength: 0.7,
    colors: ['#4a90e2', '#2d6fc7', '#74b0f0', '#1a3a6e'],
    fade: 0.02,
    sizeMin: 1, sizeMax: 3.5,
    gravity: 0.006,
  },
  {
    id: 'descent',
    label: 'Descent',
    glyph: '⟳',
    count: 130,
    speed: 0.7,
    noiseScale: 0.0013,
    noiseStrength: 1.2,
    colors: ['#7b5ea7', '#4a2d8a', '#9d7cc7', '#2d1660'],
    fade: 0.015,
    sizeMin: 1, sizeMax: 3,
    gravity: 0.015,
  },
  {
    id: 'glow',
    label: 'Glow',
    glyph: '☀',
    count: 160,
    speed: 1.1,
    noiseScale: 0.002,
    noiseStrength: 1.8,
    colors: ['#e09040', '#d97706', '#f4a855', '#92400e'],
    fade: 0.028,
    sizeMin: 1.5, sizeMax: 5,
    gravity: -0.02,
  },
]

// ── Phase → mode mapping ──────────────────────────────────────────
const PHASE_MODE: Partial<Record<string, string>> = {
  induction: 'settle',
  coherence: 'settle',
  deepen:    'descent',
  joy:       'glow',
  wake:      'zen',
}

const modeIndex = ref(1)

// ── Canvas state ──────────────────────────────────────────────────
interface Particle {
  x: number; y: number
  vx: number; vy: number
  size: number
  color: string
  life: number; maxLife: number
}

let W = 0, H = 0, dpr = 1
let ctx: CanvasRenderingContext2D | null = null
let particles: Particle[] = []
let rafId = 0
let elapsed = 0
let mx = -9999, my = -9999
let holding = false

// ── Flow field ────────────────────────────────────────────────────
function flowAngle(px: number, py: number, m: Mode): number {
  const x = px * m.noiseScale
  const y = py * m.noiseScale
  if (m.id === 'cascade') {
    return Math.PI * 0.5 + Math.sin(x * 3 + elapsed) * 0.9 + Math.cos(y * 2 + elapsed * 0.7) * 0.55
  }
  if (m.id === 'pulse') {
    const r = Math.hypot(px - W * 0.5, py - H * 0.5) * 0.006
    const ang = Math.atan2(py - H * 0.5, px - W * 0.5)
    return ang + r - elapsed * 1.8
  }
  if (m.id === 'zen') {
    const ang = Math.atan2(py - H * 0.5, px - W * 0.5)
    return ang + Math.PI * 0.5 + elapsed * 0.25
  }
  if (m.id === 'void') {
    return Math.sin(x * 1.2 + elapsed * 0.4) * Math.PI * 2.5 + Math.cos(y * 0.8 + elapsed * 0.25) * 1.2
  }
  if (m.id === 'settle') {
    // Gentle downward drift with slow lateral breath-like oscillation
    return Math.PI * 0.5
      + Math.sin(x * 0.4 + elapsed * 0.22) * 0.38
      + Math.cos(y * 0.2 + elapsed * 0.14) * 0.2
  }
  if (m.id === 'descent') {
    // Slow inward clockwise spiral — particles pulled toward center
    const ang = Math.atan2(py - H * 0.5, px - W * 0.5)
    const r = Math.hypot(px - W * 0.5, py - H * 0.5)
    const pull = 1 - Math.min(r / (Math.max(W, H) * 0.5), 1)
    return ang + Math.PI * 0.5 + pull * 0.9 + elapsed * 0.1
  }
  if (m.id === 'glow') {
    // Radial outward from center with gentle wobble
    const ang = Math.atan2(py - H * 0.5, px - W * 0.5)
    const r = Math.hypot(px - W * 0.5, py - H * 0.5)
    return ang + Math.sin(elapsed * 0.9 + r * 0.005) * 0.5
  }
  // flux (default)
  return Math.sin(x + elapsed * 0.55) * Math.PI * 2 + Math.cos(y * 1.4 + elapsed * 0.35) * Math.PI
}

// ── Particle lifecycle ────────────────────────────────────────────
function spawnParticle(m: Mode, scatter = false): Particle {
  const life = 100 + Math.random() * 140
  const color = m.colors[Math.floor(Math.random() * 4)]
  let x: number, y: number
  if (scatter) {
    x = Math.random() * W
    y = Math.random() * H
  } else {
    const edge = Math.random()
    if (edge < 0.25) { x = Math.random() * W; y = -8 }
    else if (edge < 0.5) { x = Math.random() * W; y = H + 8 }
    else if (edge < 0.75) { x = -8; y = Math.random() * H }
    else { x = W + 8; y = Math.random() * H }
    if (Math.random() < 0.45) { x = W * 0.2 + Math.random() * W * 0.6; y = H * 0.2 + Math.random() * H * 0.6 }
  }
  const angle = Math.random() * Math.PI * 2
  const spd = (0.3 + Math.random() * 0.7) * m.speed
  return {
    x, y,
    vx: Math.cos(angle) * spd,
    vy: Math.sin(angle) * spd,
    size: m.sizeMin + Math.random() * (m.sizeMax - m.sizeMin),
    color, life, maxLife: life,
  }
}

function spawnBurst(x: number, y: number, m: Mode, count: number) {
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + Math.random() * 0.3
    const spd = 2.5 + Math.random() * 5
    const life = 35 + Math.random() * 50
    particles.push({
      x, y,
      vx: Math.cos(a) * spd,
      vy: Math.sin(a) * spd,
      size: (m.sizeMin + m.sizeMax) * 0.7,
      color: m.colors[Math.floor(Math.random() * 4)],
      life, maxLife: life,
    })
  }
  // Keep cap at 2× mode count
  const cap = m.count * 2
  if (particles.length > cap) particles.splice(0, particles.length - cap)
}

function initParticles(m: Mode) {
  particles = Array.from({ length: m.count }, () => spawnParticle(m, true))
}

// ── Render loop ───────────────────────────────────────────────────
function tick() {
  if (!ctx) return
  const m = MODES[modeIndex.value]

  // Fade trail
  ctx.globalAlpha = m.fade
  ctx.fillStyle = '#0c0a12'
  ctx.fillRect(0, 0, W, H)
  ctx.globalAlpha = 1

  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]

    // Flow force
    const angle = flowAngle(p.x, p.y, m)
    p.vx += Math.cos(angle) * m.noiseStrength * 0.038
    p.vy += Math.sin(angle) * m.noiseStrength * 0.038 + m.gravity

    // Mouse / touch force
    const dx = p.x - mx, dy = p.y - my
    const dist = Math.hypot(dx, dy)
    if (dist < 150 && dist > 0.5) {
      const f = ((150 - dist) / 150) * (holding ? -1.1 : 1.4)
      p.vx += (dx / dist) * f
      p.vy += (dy / dist) * f
    }

    // Damp + cap
    p.vx *= 0.955; p.vy *= 0.955
    const spd = Math.hypot(p.vx, p.vy)
    const cap = m.speed * 3.5
    if (spd > cap) { p.vx *= cap / spd; p.vy *= cap / spd }

    p.x += p.vx; p.y += p.vy
    p.life--

    // Fade in/out alpha
    const lifeRatio = p.life / p.maxLife
    const alpha = Math.min(lifeRatio * 6, 1) * Math.min((1 - lifeRatio) * 8, 1) * 0.88

    // Mode-specific size modulation
    let sz = p.size
    if (m.id === 'pulse') sz *= 0.65 + 0.35 * Math.sin(elapsed * 3.5 + p.x * 0.012)
    if (m.id === 'settle') sz *= 0.8 + 0.2 * Math.sin(elapsed * 0.11) // breathes with ~10s period
    if (m.id === 'glow') sz *= 0.7 + 0.3 * Math.sin(elapsed * 2.2 + p.y * 0.008)

    ctx.beginPath()
    ctx.arc(p.x, p.y, Math.max(0.3, sz), 0, Math.PI * 2)
    ctx.fillStyle = p.color
    ctx.globalAlpha = alpha
    ctx.fill()
    ctx.globalAlpha = 1

    // Remove dead or escaped
    if (p.life <= 0 || p.x < -30 || p.x > W + 30 || p.y < -30 || p.y > H + 30) {
      particles[i] = spawnParticle(m, Math.random() < 0.5)
    }
  }

  // ── Breathing ring (settle / descent / coherence phase) ──────────
  if (m.id === 'settle' || m.id === 'descent') {
    const breathe = (Math.sin(elapsed * 0.11) + 1) / 2 // 0–1, ~10 s period
    const ringColor = m.id === 'descent' ? '123,94,167' : '74,144,226'
    for (let ri = 0; ri < 3; ri++) {
      const r = 45 + ri * 38 + breathe * 55
      const a = (0.1 - ri * 0.025) * breathe
      ctx.beginPath()
      ctx.arc(W * 0.5, H * 0.5, r, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(${ringColor},${a})`
      ctx.lineWidth = 1 + breathe * 0.8
      ctx.globalAlpha = 1
      ctx.stroke()
    }
  }
  if (m.id === 'glow') {
    const pulse = (Math.sin(elapsed * 0.22) + 1) / 2
    for (let ri = 0; ri < 4; ri++) {
      const r = 35 + ri * 42 + pulse * 50
      ctx.beginPath()
      ctx.arc(W * 0.5, H * 0.5, r, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(224,144,64,${(0.08 - ri * 0.015) * pulse})`
      ctx.lineWidth = 1
      ctx.globalAlpha = 1
      ctx.stroke()
    }
  }

  // ── Text overlay (trance instruction > story word) ────────────────
  const overlayText = sessionActive.value && currentInstruction.value
    ? currentInstruction.value
    : currentWord.value
  if (overlayText) {
    const isInstruction = sessionActive.value && !!currentInstruction.value
    const isFocused = m.id === 'zen' || m.id === 'settle' || m.id === 'descent'
    const sz = isFocused
      ? Math.min(W * 0.075, 58)
      : Math.min(W * 0.065, 44)
    const alpha = isFocused ? (isInstruction ? 0.88 : 0.78) : (isInstruction ? 0.55 : 0.22)
    ctx.globalAlpha = alpha
    ctx.font = `200 ${sz}px 'SF Pro Display', system-ui, sans-serif`
    ctx.fillStyle = isInstruction ? (phaseAccent.value || m.colors[2]) : m.colors[2]
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    // Wrap long instruction text
    if (isInstruction && overlayText.length > 30) {
      const words = overlayText.split(' ')
      const mid = Math.ceil(words.length / 2)
      const line1 = words.slice(0, mid).join(' ')
      const line2 = words.slice(mid).join(' ')
      const lineH = sz * 1.45
      ctx.fillText(line1, W * 0.5, H * 0.5 - lineH * 0.5)
      ctx.fillText(line2, W * 0.5, H * 0.5 + lineH * 0.5)
    } else {
      ctx.fillText(overlayText, W * 0.5, H * 0.5)
    }
    ctx.globalAlpha = 1
  }

  elapsed += 0.003
  rafId = requestAnimationFrame(tick)
}

// ── Resize ────────────────────────────────────────────────────────
function resize() {
  const c = canvas.value; if (!c) return
  dpr = Math.min(devicePixelRatio, 2)
  W = c.clientWidth; H = c.clientHeight
  c.width = W * dpr; c.height = H * dpr
  ctx = c.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.fillStyle = '#0c0a12'
  ctx.fillRect(0, 0, W, H)
}

// ── Mode switching ────────────────────────────────────────────────
function setMode(i: number) {
  modeIndex.value = i
  // Fade old particles out fast
  particles.forEach(p => { p.life = Math.min(p.life, 25) })
  // Seed fresh particles for new mode
  const m = MODES[i]
  const fresh = Array.from({ length: Math.floor(m.count * 0.4) }, () => spawnParticle(m, true))
  particles.push(...fresh)
  // Morph audio
  if (audioReady) {
    const cfg = AUDIO_MODES[m.id] ?? AUDIO_MODES.flux
    applyAudioMode(m.id, 1.4)
    restartBeat(m.id, cfg)
  }
}

function prevMode() { setMode((modeIndex.value - 1 + MODES.length) % MODES.length) }
function nextMode() { setMode((modeIndex.value + 1) % MODES.length) }

// ── Canvas interaction ────────────────────────────────────────────
function onMouseMove(e: MouseEvent) { mx = e.clientX; my = e.clientY }
function onMouseDown(e: MouseEvent) {
  holding = true
  spawnBurst(e.clientX, e.clientY, MODES[modeIndex.value], 28)
  startAudio()
}
function onMouseUp() { holding = false }
function onMouseLeave() { mx = -9999; my = -9999; holding = false }
function onTouchMove(e: TouchEvent) {
  const t = e.touches[0]; mx = t.clientX; my = t.clientY
}
function onTouchStart(e: TouchEvent) {
  const t = e.touches[0]; mx = t.clientX; my = t.clientY
  holding = true
  spawnBurst(t.clientX, t.clientY, MODES[modeIndex.value], 28)
  startAudio()
}
function onTouchEnd() { holding = false; mx = -9999; my = -9999 }

// ── Carousel swipe ────────────────────────────────────────────────
let swipeX = 0
function onCarouselSwipeStart(e: TouchEvent) { swipeX = e.touches[0].clientX }
function onCarouselSwipeEnd(e: TouchEvent) {
  const delta = e.changedTouches[0].clientX - swipeX
  if (Math.abs(delta) > 36) delta < 0 ? nextMode() : prevMode()
}

// ── Keyboard ──────────────────────────────────────────────────────
function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.key === 'ArrowLeft') prevMode()
  if (e.key === 'ArrowRight') nextMode()
}

// ── Trance phase auto-switch ──────────────────────────────────────
watch([phase, sessionActive], () => {
  if (!sessionActive.value) return
  const targetId = PHASE_MODE[phase.value]
  if (!targetId) return
  const idx = MODES.findIndex(m => m.id === targetId)
  if (idx >= 0 && idx !== modeIndex.value) setMode(idx)
})

onMounted(() => {
  logEvent('zeromind_session_started')
  resize()
  initParticles(MODES[modeIndex.value])
  rafId = requestAnimationFrame(tick)
  window.addEventListener('resize', () => { resize(); initParticles(MODES[modeIndex.value]) })
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  cancelAnimationFrame(rafId)
  window.removeEventListener('keydown', onKeyDown)
  destroyAudio()
})
</script>

<template>
  <div class="zeromind">
    <canvas
      ref="canvas"
      class="zeromind-canvas"
      aria-label="Interactive cosmic orb field — use arrow keys or WASD to push orbs"
      role="img"
      @mousemove="onMouseMove"
      @mousedown.prevent="onMouseDown"
      @mouseup="onMouseUp"
      @mouseleave="onMouseLeave"
      @touchmove.prevent="onTouchMove"
      @touchstart.prevent="onTouchStart"
      @touchend="onTouchEnd"
    />

    <!-- Screen-reader live region: mirrors trance instruction / story word from canvas -->
    <div class="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {{ sessionActive && currentInstruction ? currentInstruction : currentWord }}
    </div>

    <!-- Mode carousel -->
    <nav
      class="mode-carousel"
      aria-label="Trance mode selector"
      @touchstart.stop="onCarouselSwipeStart"
      @touchend.stop="onCarouselSwipeEnd"
    >
      <button class="carousel-arrow" @click="prevMode" aria-label="Previous mode">‹</button>

      <div class="carousel-track">
        <button
          v-for="(m, i) in MODES"
          :key="m.id"
          :class="['mode-chip', { 'mode-chip--active': i === modeIndex }]"
          :style="{ '--c': m.colors[2], '--cd': m.colors[0] }"
          :aria-pressed="i === modeIndex"
          @click="setMode(i)"
        >
          <span class="chip-glyph" aria-hidden="true">{{ m.glyph }}</span>
          <span class="chip-label">{{ m.label }}</span>
        </button>
      </div>

      <button class="carousel-arrow" @click="nextMode" aria-label="Next mode">›</button>
    </nav>

    <!-- Trance phase badge — visible when a session is active -->
    <Transition name="badge-fade">
      <div
        v-if="sessionActive && phase !== 'idle'"
        class="phase-badge"
        :style="{ '--accent': phaseAccent }"
        aria-live="polite"
        aria-atomic="true"
      >
        <span class="badge-dot" aria-hidden="true" />
        {{ phaseDisplayName }}
      </div>
    </Transition>

    <!-- Post-trance microdose overlay -->
    <PostTranceOverlay
      v-if="showOverlay && completedSession"
      :coherence="completedSession.coherence"
      :sync-count="completedSession.syncCount"
      :session-duration="completedSession.sessionDurationMs"
      :dominant-phase="completedSession.dominantPhase"
      @close="handleOverlayClose"
    />
  </div>
</template>

<style scoped>
.zeromind {
  position: absolute;
  inset: 0;
  background: #0c0a12;
  overflow: hidden;
  user-select: none;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.zeromind-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
  touch-action: none;
}

/* ── Carousel ── */
.mode-carousel {
  position: absolute;
  bottom: 2.5rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: rgba(12, 10, 18, 0.72);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 3rem;
  padding: 0.45rem 0.65rem;
  z-index: 10;
}

.carousel-arrow {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.35);
  font-size: 1.5rem;
  line-height: 1;
  padding: 0.1rem 0.3rem;
  cursor: pointer;
  transition: color 0.15s;
  flex-shrink: 0;
}
.carousel-arrow:hover { color: rgba(255, 255, 255, 0.8); }

.carousel-track {
  display: flex;
  gap: 0.3rem;
}

.mode-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 2rem;
  padding: 0.45rem 0.85rem;
  cursor: pointer;
  transition:
    background 0.2s,
    border-color 0.2s,
    transform 0.2s,
    opacity 0.2s;
  opacity: 0.45;
  transform: scale(0.9);
  color: rgba(255, 255, 255, 0.7);
  min-width: 3.6rem;
}

.mode-chip:hover {
  opacity: 0.75;
  transform: scale(0.95);
}

.mode-chip--active {
  background: color-mix(in srgb, var(--cd) 25%, transparent);
  border-color: color-mix(in srgb, var(--c) 50%, transparent);
  opacity: 1;
  transform: scale(1.05);
  color: var(--c);
}

.chip-glyph {
  font-size: 1.2rem;
  line-height: 1;
  font-family: 'SF Pro Display', system-ui, sans-serif;
}

.chip-label {
  font-size: 0.65rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 500;
}

/* ── Phase badge ── */
.phase-badge {
  position: absolute;
  top: 1.25rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.85rem;
  background: rgba(12, 10, 18, 0.65);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  border-radius: 2rem;
  font-size: 0.62rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  z-index: 10;
  pointer-events: none;
  white-space: nowrap;
}

.badge-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  animation: badge-pulse 2s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50%       { opacity: 1;   transform: scale(1.2); }
}

.badge-fade-enter-active,
.badge-fade-leave-active { transition: opacity 0.8s ease; }
.badge-fade-enter-from,
.badge-fade-leave-to     { opacity: 0; }
</style>
