<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import * as Tone from 'tone'
import { useFractionationSession, type FracStage } from '@/composables/useFractionation'
import { useEyeState } from '@/composables/useEyeState'
import { useVoice } from '@/composables/useVoice'
import { useTranceEngine } from '@/composables/useTranceEngine'

/**
 * Fractionation overlay for the Zeromind visuals: a consent card before the
 * session (camera and natural voice are both opt-in), then a small corner HUD
 * while the runner drives the engine and voice.
 */

const session = useFractionationSession()
const { stage, round, rounds, running, camera } = session
const eye = useEyeState()
const voice = useVoice()
const { completedSession } = useTranceEngine()

const useCamera = ref(false)
const naturalVoice = ref(voice.backend.value === 'kokoro')
const preparing = ref(false)
const note = ref('')
let disposed = false

// ── Natural voice (kokoro) ────────────────────────────────────────
// Turning it on starts the one-time download right away, so it can overlap
// with reading the card. Begin waits for it, or the person can skip it.
let kokoroTask: Promise<boolean> | null = null
let skipVoiceWait: (() => void) | null = null

function startKokoro(): Promise<boolean> {
  if (!kokoroTask || voice.kokoroStatus.value === 'error') {
    kokoroTask = voice.enableKokoro().then((ok) => {
      // Turned off while it downloaded: stay on the system voice.
      if (ok && !naturalVoice.value) voice.disableKokoro()
      return ok
    })
  }
  return kokoroTask
}

function toggleVoice() {
  naturalVoice.value = !naturalVoice.value
  if (naturalVoice.value) void startKokoro()
  else {
    voice.disableKokoro()
    skipVoiceWait?.()
  }
}

const voiceStatus = computed(() => {
  if (!naturalVoice.value) return 'Uses your browser’s built-in voice.'
  switch (voice.kokoroStatus.value) {
    case 'downloading': return 'Downloading the voice (about 90 MB, once)…'
    case 'ready': return 'Natural voice ready.'
    case 'error': return 'The natural voice couldn’t load, so the browser voice will be used.'
    default: return 'Downloads about 90 MB once, then stays in your browser.'
  }
})

// ── Begin ─────────────────────────────────────────────────────────
async function begin() {
  if (preparing.value || running.value) return
  preparing.value = true
  note.value = ''
  // Unlock Web Audio inside the click (the engine starts after the awaits).
  void Tone.start().catch(() => { /* engine retries */ })

  const waits: Promise<unknown>[] = []
  if (naturalVoice.value) {
    waits.push(Promise.race([startKokoro(), new Promise<void>((r) => { skipVoiceWait = r })]))
  }
  if (useCamera.value) waits.push(eye.start())
  await Promise.all(waits)
  skipVoiceWait = null

  let withCamera = false
  if (useCamera.value) {
    const s = eye.status.value
    withCamera = s === 'tracking' || s === 'no-face'
    if (!withCamera) {
      eye.stop()
      note.value = s === 'denied'
        ? 'Camera access wasn’t allowed, so the session will use gentle timing instead.'
        : 'The camera couldn’t start, so the session will use gentle timing instead.'
    }
  }

  if (disposed) return
  try {
    await session.start({ camera: withCamera })
  } catch (err) {
    console.warn('[FractionationSession] could not start', err)
    note.value = 'The session couldn’t start audio. Try Begin again.'
  } finally {
    preparing.value = false
  }
}

function skipVoice() {
  naturalVoice.value = false
  voice.disableKokoro()
  skipVoiceWait?.()
}

onUnmounted(() => {
  disposed = true
  skipVoiceWait?.()
})

// ── HUD ───────────────────────────────────────────────────────────
const STAGE_WORDS: Record<FracStage, string> = {
  idle: '',
  induce: 'settling in',
  descend: 'eyes closing',
  hold: 'resting deeper',
  emerge: 'coming up',
  reinduce: 'going back down',
  final: 'resting',
  done: 'finished',
}
const stageWords = computed(() => STAGE_WORDS[stage.value])

const eyeLabel = computed(() => {
  if (!camera.value) return 'timed'
  switch (eye.status.value) {
    case 'tracking': return eye.eyesClosed.value ? 'closed' : 'open'
    case 'no-face': return 'no face'
    case 'loading': return 'camera…'
    default: return 'timed'
  }
})

const showCard = computed(() => !running.value && !completedSession.value)
</script>

<template>
  <div class="frac">
    <Transition name="frac-fade">
      <section v-if="showCard" class="card dmt-card dmt-card--prism" aria-labelledby="frac-title">
        <p class="dmt-eyebrow">Practice</p>
        <h1 id="frac-title" class="title">Fractionation</h1>
        <p class="lede">
          A calm voice guides you into trance, then briefly brings you back out, then guides you
          in again. Each return tends to go deeper than the last. It takes about 6–8 minutes.
          Headphones are recommended.
        </p>

        <div class="option">
          <button
            type="button"
            class="toggle dmt-chip"
            :class="{ 'dmt-chip--on': useCamera }"
            role="switch"
            :aria-checked="useCamera"
            data-test="camera-toggle"
            :disabled="preparing"
            @click="useCamera = !useCamera"
          >
            Use my camera to follow my eyes
          </button>
          <p class="hint" data-test="privacy-note">
            Runs entirely on this device. No video leaves your browser or is stored. Eye closure
            only paces the session. It isn’t a measure of trance.
            <template v-if="!useCamera"> Without the camera, the session uses gentle timing.</template>
          </p>
        </div>

        <div class="option">
          <button
            type="button"
            class="toggle dmt-chip"
            :class="{ 'dmt-chip--on': naturalVoice }"
            role="switch"
            :aria-checked="naturalVoice"
            data-test="voice-toggle"
            :disabled="preparing"
            @click="toggleVoice"
          >
            Natural voice
          </button>
          <p class="hint" aria-live="polite">{{ voiceStatus }}</p>
        </div>

        <p v-if="note" class="note" role="status">{{ note }}</p>

        <div class="actions">
          <button
            type="button"
            class="dmt-btn dmt-btn--prism"
            data-test="begin"
            :disabled="preparing"
            @click="begin"
          >
            {{ preparing ? 'Getting ready…' : 'Begin' }}
          </button>
          <button
            v-if="preparing && naturalVoice && voice.kokoroStatus.value === 'downloading'"
            type="button"
            class="link"
            @click="skipVoice"
          >
            use the browser voice instead
          </button>
        </div>
      </section>
    </Transition>

    <Transition name="frac-fade">
      <div v-if="running" class="hud dmt-card" role="status" aria-live="polite">
        <span class="hud-round">round {{ round }} of {{ rounds }}</span>
        <span class="hud-stage">{{ stageWords }}</span>
        <span class="hud-eye" :class="{ 'hud-eye--closed': eyeLabel === 'closed' }">{{ eyeLabel }}</span>
        <button type="button" class="link" data-test="end" @click="session.stop()">end</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* Look comes from src/styles/dmt.css; layout only here. */
.frac {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: none;
  color: var(--dmt-ink);
}
.frac > * { pointer-events: auto; }

.card {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(440px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  padding: 24px 22px 20px;
}
.title {
  margin: 6px 0 10px;
  font-size: 24px;
  font-weight: 300;
  letter-spacing: 0.04em;
}
.lede {
  font-size: 13.5px;
  line-height: 1.6;
  font-weight: 300;
  color: var(--dmt-ink-dim);
  margin-bottom: 16px;
}

.option { margin-bottom: 14px; }
.toggle {
  padding: 8px 14px;
  font-size: 12.5px;
  cursor: pointer;
}
.toggle:disabled { opacity: 0.5; cursor: default; }
.hint {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--dmt-ink-faint);
}
.note {
  font-size: 12px;
  line-height: 1.5;
  color: var(--dmt-amber);
  margin-bottom: 12px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.hud {
  position: absolute;
  right: 16px;
  bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--dmt-ink-dim);
  opacity: 0.7;
  transition: opacity 0.6s ease;
}
.hud:hover, .hud:focus-within { opacity: 1; }
.hud-stage { color: var(--dmt-ink); }
.hud-eye {
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--dmt-edge);
  font-size: 10px;
  color: var(--dmt-ink-faint);
}
.hud-eye--closed { color: var(--dmt-cyan); }

.link {
  background: none;
  border: none;
  padding: 0;
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--dmt-ink-faint);
  cursor: pointer;
  transition: color 0.3s;
}
.link:hover { color: var(--dmt-ink); }

.frac-fade-enter-active, .frac-fade-leave-active { transition: opacity 0.8s ease; }
.frac-fade-enter-from, .frac-fade-leave-to { opacity: 0; }

@media (max-width: 480px) {
  .hud { left: 16px; right: 16px; bottom: 64px; justify-content: space-between; gap: 8px; }
}
</style>
