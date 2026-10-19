<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useCosmicPhysics } from '@/composables/useCosmicPhysics'

const bgCanvas = ref<HTMLCanvasElement>()
const { init: initCosmic, destroy: destroyCosmic } = useCosmicPhysics(bgCanvas, {
  particleCount: 60,
  starCount: 80,
  enableKeyboard: false,
  enableMouseInteract: true,
  clearAlpha: 0.06,
  mouseAttractForce: 0.3,
})

onMounted(() => initCosmic())
onUnmounted(() => destroyCosmic())

interface Session {
  title: string
  path: string
  description: string
  featured?: boolean
}

interface Group {
  label: string
  sessions: Session[]
}

const groups: Group[] = [
  {
    label: 'Authoring',
    sessions: [
      {
        title: 'Glass Studio',
        path: '/studio',
        description: 'Upload video or audio, layer subliminal text overlays, and compose real binaural entrainment — then export the finished composition.',
        featured: true
      },
      {
        title: 'Story Studio',
        path: '/story',
        description: 'Write a story in beats and export it as a video: voiced lines, phrase overlays and a binaural beat that deepens with the story, over your own footage.'
      }
    ]
  },
  {
    label: 'Reading & Narrative',
    sessions: [
      {
        title: 'Reader',
        path: '/reader',
        description: 'Phrase-paced text reader for guided focus and suggestion.'
      },
      {
        title: 'Hypno',
        path: '/hypno',
        description: 'Hypnotic text presentation paired with rhythmic visuals.'
      }
    ]
  },
  {
    label: 'Sound & Entrainment',
    sessions: [
      {
        title: 'Audio',
        path: '/audio',
        description: 'Layered ambient mixer for background entrainment.'
      },
      {
        title: 'WebAudio',
        path: '/webaudio',
        description: 'Full visual binaural session with raw Web Audio engine.'
      },
      {
        title: 'Trance',
        path: '/trance',
        description: 'Guided binaural journey with phase-driven coherence.'
      }
    ]
  },
  {
    label: 'Visual',
    sessions: [
      {
        title: 'Liquid Glass',
        path: '/liquidglass',
        description: 'Refractive moving-glass visual field for soft focus.'
      },
      {
        title: 'Spiral',
        path: '/spiral',
        description: 'Slow spiral induction loop for fixated attention.'
      },
      {
        title: 'ZeroMind',
        path: '/zeromind',
        description: 'Star tunnel visualization for dreamlike absorption.'
      }
    ]
  }
]
</script>

<template>
  <main class="sessions">
    <canvas ref="bgCanvas" class="sessions-bg" />
    <header class="sessions-head">
      <h1>Sessions</h1>
      <p class="lede">Pick a tool. Each session is one route into Enfractionation.</p>
    </header>

    <section v-for="group in groups" :key="group.label" class="group">
      <h2 class="group-label">{{ group.label }}</h2>
      <div class="grid">
        <RouterLink
          v-for="s in group.sessions"
          :key="s.path"
          :to="s.path"
          class="card"
          :class="{ 'card--featured': s.featured }"
        >
          <h3 class="card-title">{{ s.title }}</h3>
          <p class="card-desc">{{ s.description }}</p>
          <span class="card-cta">Open</span>
        </RouterLink>
      </div>
    </section>
  </main>
</template>

<style scoped>
.sessions {
  position: relative;
  min-height: 100vh;
  background: transparent;
  color: #e2e8f0;
  padding: 3rem 1.25rem 4rem;
  max-width: 1080px;
  margin: 0 auto;
  font-family: inherit;
}

.sessions-bg {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}

.sessions-head {
  position: relative;
  z-index: 1;
  margin-bottom: 2.5rem;
}

.group {
  position: relative;
  z-index: 1;
  margin-bottom: 2.5rem;
}

.sessions-head h1 {
  font-size: 2rem;
  font-weight: 500;
  margin: 0 0 0.5rem;
  letter-spacing: 0.01em;
}

.lede {
  margin: 0;
  color: #94a3b8;
  font-size: 0.95rem;
  line-height: 1.6;
}

.group-label {
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #64748b;
  margin: 0 0 1rem;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 1.1rem 1.25rem;
  background: rgba(10, 10, 25, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.6rem;
  text-decoration: none;
  color: inherit;
  backdrop-filter: blur(8px);
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  background: rgba(15, 15, 35, 0.75);
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.08);
}

.card:focus-visible {
  outline: 2px solid rgba(99, 102, 241, 0.8);
  outline-offset: 2px;
  border-color: rgba(99, 102, 241, 0.5);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.1);
}

.card--featured {
  border-color: rgba(129, 140, 248, 0.2);
  background: rgba(10, 10, 30, 0.75);
}

.card--featured:hover {
  border-color: rgba(129, 140, 248, 0.45);
  box-shadow: 0 0 28px rgba(99, 102, 241, 0.12);
}

.card-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
  color: #e2e8f0;
}

.card-desc {
  margin: 0;
  color: #94a3b8;
  font-size: 0.85rem;
  line-height: 1.5;
}

.card-cta {
  margin-top: 0.25rem;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

@media (min-width: 720px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
  }
}

@media (min-width: 1000px) {
  .grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
