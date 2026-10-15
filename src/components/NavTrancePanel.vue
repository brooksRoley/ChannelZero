<script setup lang="ts">
import { computed } from 'vue'
import { useTranceEngine } from '@/composables/useTranceEngine'

const {
  sessionActive: tranceSessionActive,
  phase: trancePhase,
  coherenceScore: tranceCoherence,
  phaseAccent: tranceAccent,
  phaseDisplayName,
  activeLayerCount,
  totalLayers,
  startSession: tranceStart,
  stopSession: tranceStop,
  windDown: tranceWindDown,
  baselineModulatorActive,
  ptosisInducerActive,
  avSyncActive,
  alphaWaveActive,
  thetaDreamActive,
  schumannActive,
  solfeggioActive,
  toggleBaselineModulator,
  togglePtosisInducer,
  toggleAVSync,
  toggleAlphaWave,
  toggleThetaDream,
  toggleSchumann,
  toggleSolfeggio,
} = useTranceEngine()

const toneLayers = computed(() => [
  {
    key: 'alpha', name: 'Alpha Flow', desc: '10 Hz · binaural',
    active: alphaWaveActive.value, toggle: toggleAlphaWave,
    tooltip: '195 Hz left / 205 Hz right → 10 Hz perceived beat.\nAlpha entrainment for relaxed focus and flow state.\nUse at session start or during coherence phase.\n⚠ Requires headphones.',
  },
  {
    key: 'theta', name: 'Deep Theta', desc: '6 Hz · binaural',
    active: thetaDreamActive.value, toggle: toggleThetaDream,
    tooltip: '177 Hz left / 183 Hz right → 6 Hz perceived beat.\nTheta band deepens meditation and invites hypnagogic imagery.\nBest activated during descent phase.\n⚠ Requires headphones.',
  },
  {
    key: 'schumann', name: 'Earth Tone', desc: '7.83 Hz · binaural',
    active: schumannActive.value, toggle: toggleSchumann,
    tooltip: '246 Hz left / 254 Hz right → 7.83 Hz perceived beat.\nEarth\'s Schumann resonance — grounding and coherence.\nLayer lightly under a dominant binaural beat.\n⚠ Requires headphones.',
  },
  {
    key: 'baseline', name: 'Nerve Pulse', desc: '2.4 Hz · isochronic',
    active: baselineModulatorActive.value, toggle: toggleBaselineModulator,
    tooltip: '432 Hz carrier · 2.4 Hz amplitude modulation.\nIsochronic delta pulse — no headphones required.\nPairs with Pulse Sync for audiovisual reinforcement.\nSlower than theta; most effective in deep descent.',
  },
  {
    key: 'ptosis', name: 'Drift', desc: '0.5 Hz · noise sweep',
    active: ptosisInducerActive.value, toggle: togglePtosisInducer,
    tooltip: 'Pink noise through a swept lowpass filter.\nCutoff oscillates 100–800 Hz at 0.5 Hz, slowly drifting\nto 0.42 Hz over 5 min to prevent neural adaptation.\nSupports eyelid heaviness and bodily surrender.',
  },
  {
    key: 'av', name: 'Pulse Sync', desc: '2.4 Hz · AV lock',
    active: avSyncActive.value, toggle: toggleAVSync,
    tooltip: '144 BPM synth pulse (2.4 beat/s).\nAudiovisual isochronic entrainment — aligns with\nNerve Pulse frequency for reinforced delta rhythm.\nVisual flash fires in lockstep with the audio pulse.',
  },
  {
    key: 'solfeg', name: 'Restore', desc: '528 Hz · solfeggio',
    active: solfeggioActive.value, toggle: toggleSolfeggio,
    tooltip: '528 Hz pure sine with 1 Hz tremolo.\nSolfeggio "miracle tone" associated with restoration\nand cellular coherence. Gentle, always-on presence —\nsafe to layer under any other module.',
  },
])

const canWindDown = computed(() =>
  tranceSessionActive.value && (trancePhase.value === 'deepen' || trancePhase.value === 'joy')
)
</script>

<template>
  <div class="panel-section trance-section">
    <div class="trance-header">
      <span class="section-label" :style="tranceSessionActive ? { color: tranceAccent } : {}">Trance</span>
      <div v-if="activeLayerCount > 0" class="depth-meter">
        <span class="depth-label">depth</span>
        <span
          v-for="i in totalLayers"
          :key="i"
          class="depth-dot"
          :class="{ filled: i <= activeLayerCount }"
        />
      </div>
    </div>

    <div class="section-row">
      <button
        class="panel-btn"
        :class="{ 'panel-btn--active': tranceSessionActive }"
        @click="tranceSessionActive ? tranceStop() : tranceStart()"
      >
        {{ tranceSessionActive ? '&#9632; End' : '&#9654; Journey' }}
      </button>
      <span v-if="tranceSessionActive && phaseDisplayName" class="phase-pill" :style="{ borderColor: tranceAccent, color: tranceAccent }">
        {{ phaseDisplayName }}
        <template v-if="trancePhase === 'coherence'"> &middot; {{ tranceCoherence }}%</template>
      </span>
      <button
        v-if="canWindDown"
        class="panel-btn"
        @click="tranceWindDown()"
      >
        Wind Down
      </button>
    </div>

    <div class="tone-layers">
      <button
        v-for="layer in toneLayers"
        :key="layer.key"
        class="tone-chip"
        :class="{ 'tone-chip--active': layer.active }"
        @click="layer.toggle()"
      >
        <span class="tone-tip">{{ layer.tooltip }}</span>
        <span class="tone-name">{{ layer.name }}</span>
        <span class="tone-desc">{{ layer.desc }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Shared panel primitives (owned by NavBar, duplicated here for inner-element scope) */
.section-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.section-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.panel-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  padding: 0.3rem 0.6rem;
  border-radius: 0.35rem;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
}

.panel-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

.panel-btn--active {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.4);
  color: #e2e8f0;
}

/* Trance-specific */
.trance-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.trance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.depth-meter {
  display: flex;
  align-items: center;
  gap: 3px;
}

.depth-label {
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #475569;
  margin-right: 4px;
}

.depth-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  transition: background 0.3s, box-shadow 0.3s;
}

.depth-dot.filled {
  background: #6366f1;
  box-shadow: 0 0 6px rgba(99, 102, 241, 0.5);
}

.phase-pill {
  font-size: 0.7rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.2rem 0.6rem;
  border: 1px solid;
  border-radius: 1rem;
  font-variant-numeric: tabular-nums;
}

.tone-layers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.tone-chip {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.5rem;
  padding: 0.35rem 0.6rem;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 5rem;
  font-family: inherit;
  color: #94a3b8;
}

.tone-chip:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
  color: #cbd5e1;
}

.tone-chip--active {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.4);
  color: #e2e8f0;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.15);
}

.tone-chip--active:hover {
  background: rgba(99, 102, 241, 0.25);
}

.tone-name {
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.2;
}

.tone-desc {
  font-size: 0.55rem;
  letter-spacing: 0.06em;
  color: #64748b;
  text-transform: lowercase;
}

.tone-chip--active .tone-desc {
  color: rgba(165, 180, 252, 0.6);
}

.tone-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: 220px;
  max-width: min(220px, calc(100vw - 2rem));
  background: rgba(10, 8, 20, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.55rem;
  padding: 0.55rem 0.7rem;
  font-size: 0.6rem;
  line-height: 1.65;
  color: #94a3b8;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.18s ease;
  z-index: 200;
  text-transform: none;
  text-align: left;
  white-space: pre-line;
  letter-spacing: 0.01em;
  font-weight: 400;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
}

.tone-tip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: rgba(10, 8, 20, 0.97);
}

.tone-chip:hover .tone-tip {
  opacity: 1;
}

.tone-chip--active .tone-tip {
  border-color: rgba(99, 102, 241, 0.25);
  color: #a5b4fc;
}

@media (min-width: 769px) {
  .trance-section {
    flex-direction: column !important;
    align-items: stretch !important;
  }

  .section-label {
    font-size: 0.7rem;
  }
}
</style>
