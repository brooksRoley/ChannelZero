<script setup lang="ts">
import { ref, computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { usePracticeJourney, signed, type PracticeEntry } from '@/composables/usePracticeJourney'
import { useReflection, type Reading } from '@/composables/useReflection'
import { recommendPractice } from '@/composables/usePracticeLog'
import { METHODS, METHOD_ORDER, SESSION_TO_METHOD, type MethodId } from '@/data/practiceMethods'

const router = useRouter()
const route = useRoute()
const {
  entries, pending, thread, familiarityByMethod, overallShift, observations,
  begin, finish, abandon, markEnded,
} = usePracticeJourney()
const { localOnly, setLocalOnly, reflect } = useReflection()

// 1 = tight/heavy … 5 = open/at ease
const SCALE = ['tight', 'uneasy', 'in between', 'easy', 'open']

// ── Choosing a method ─────────────────────────────────────────────
const suggestion = recommendPractice(new Date().getHours(), null)
const suggested = SESSION_TO_METHOD[suggestion.session] ?? 'zeromind'
const fromQuery = String(route.query.method ?? '') as MethodId
const chosen = ref<MethodId>(fromQuery in METHODS ? fromQuery : suggested)
const method = computed(() => METHODS[chosen.value])

// ── Before check ──────────────────────────────────────────────────
const beforeRating = ref(3)
const beforeText = ref('')
const beforeReading = ref<Reading | null>(null)
const starting = ref(false)

async function start() {
  starting.value = true
  let reading: Reading | undefined
  if (beforeText.value.trim()) {
    reading = await reflect(
      { method: chosen.value, moment: 'before', prompt: method.value.prompts.before, text: beforeText.value, before: beforeRating.value },
      (local) => { beforeReading.value = local },
      4000, // don't hold the door for long
    )
  }
  const to = begin(chosen.value, { rating: beforeRating.value, text: beforeText.value.trim() || undefined, reading })
  starting.value = false
  router.push(to)
}

// ── After check ───────────────────────────────────────────────────
const pendingMethod = computed(() => (pending.value ? METHODS[pending.value.method] : null))
const afterRating = ref(3)
const afterText = ref('')
const afterReading = ref<Reading | null>(null)
const finished = ref<PracticeEntry | null>(null)
const finishing = ref(false)

async function complete() {
  if (!pending.value) return
  finishing.value = true
  markEnded()
  let reading: Reading | undefined
  if (afterText.value.trim()) {
    reading = await reflect(
      {
        method: pending.value.method, moment: 'after', prompt: pendingMethod.value!.prompts.after,
        text: afterText.value, before: pending.value.before.rating, after: afterRating.value,
      },
      (local) => { afterReading.value = local },
    )
    afterReading.value = reading
  }
  finished.value = finish({ rating: afterRating.value, text: afterText.value.trim() || undefined, reading })
  finishing.value = false
  afterText.value = ''
}

function startAnother() {
  finished.value = null
  afterReading.value = null
  beforeText.value = ''
  beforeReading.value = null
}

const shiftLine = computed(() => {
  const e = finished.value
  if (!e?.after) return ''
  const d = e.after.rating - e.before.rating
  if (d > 0) return `You came in ${SCALE[e.before.rating - 1]} and left ${SCALE[e.after.rating - 1]}.`
  if (d < 0) return `You left feeling more ${SCALE[e.after.rating - 1]} than you came in. That’s worth knowing too.`
  return `You came in and left ${SCALE[e.after.rating - 1]}. Steady is a result.`
})

const recent = computed(() => entries.value.slice(0, 5))
const threadDays = computed(() => thread.value.filter(Boolean).length)

function fmtDay(t: number) {
  return new Date(t).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="dmt-field practice-root">
  <div class="practice">
    <header class="head">
      <h1 class="dmt-title">Practice</h1>
      <p>Learn a method, try it, and notice what changes. Everything here stays on this device.</p>
    </header>

    <!-- ── Finished: the mirror ── -->
    <section v-if="finished" class="panel dmt-card dmt-card--prism">
      <p class="dmt-eyebrow">{{ METHODS[finished.method].name }} · done</p>
      <p class="shift">{{ shiftLine }}</p>
      <p v-if="afterReading" class="reflection">
        <span class="tone">{{ afterReading.tone }}</span>{{ afterReading.reflection }}
      </p>
      <ul v-if="finished.during.length" class="during">
        <li v-for="(n, i) in finished.during" :key="i">
          <span class="muted">{{ n.prompt }}</span> {{ n.text }} <span class="tone tone--inline">{{ n.tone }}</span>
        </li>
      </ul>
      <button class="dmt-btn" @click="startAnother">Back to practice</button>
    </section>

    <!-- ── A session is open: after-check ── -->
    <section v-else-if="pending && pendingMethod" class="panel dmt-card dmt-card--prism">
      <p class="dmt-eyebrow">{{ pendingMethod.name }} · {{ pending.sessionEndedAt ? 'finished' : 'in progress' }}</p>
      <template v-if="pending.sessionEndedAt">
        <h2>{{ pendingMethod.prompts.after }}</h2>
        <div class="scale" role="radiogroup" aria-label="How do you feel now?">
          <button
            v-for="(w, i) in SCALE" :key="w" role="radio" :aria-checked="afterRating === i + 1"
            class="scale-step dmt-chip" :class="{ 'dmt-chip--on': afterRating === i + 1 }" @click="afterRating = i + 1"
          >{{ w }}</button>
        </div>
        <p class="muted small">You started at “{{ SCALE[pending.before.rating - 1] }}”.</p>
        <textarea v-model="afterText" rows="2" maxlength="600" placeholder="a few words, if you like…" class="field dmt-input" />
        <button class="dmt-btn dmt-btn--prism" :disabled="finishing" @click="complete">
          {{ finishing ? 'Reading…' : 'Close the session' }}
        </button>
      </template>
      <template v-else>
        <p class="muted">Your session is still open.</p>
        <div class="row">
          <button class="dmt-btn dmt-btn--prism" @click="router.push(pendingMethod.route)">Return to it</button>
          <button class="dmt-btn" @click="markEnded">I finished it</button>
          <button class="dmt-btn btn--ghost" @click="abandon">Let it go</button>
        </div>
      </template>
    </section>

    <!-- ── Choose + learn + before-check ── -->
    <template v-else>
      <section class="methods" aria-label="Methods">
        <button
          v-for="id in METHOD_ORDER" :key="id"
          class="method dmt-chip" :class="{ 'dmt-chip--on': chosen === id }" @click="chosen = id"
        >
          <span class="method-name">{{ METHODS[id].name }}</span>
          <span class="method-meta">{{ familiarityByMethod[id].label }} · {{ METHODS[id].minutes }} min</span>
          <span class="method-bar"><span :style="{ width: `${familiarityByMethod[id].progress * 100}%` }" /></span>
          <span v-if="id === suggested" class="method-tag">suggested now</span>
        </button>
      </section>

      <section class="panel dmt-card">
        <p class="dmt-eyebrow">{{ method.name }}<span v-if="method.needsHeadphones"> · headphones</span></p>
        <p class="what">{{ method.what }}</p>
        <p v-if="chosen === suggested" class="muted small">{{ suggestion.reason }}</p>
        <ol class="how">
          <li v-for="(step, i) in method.how" :key="i">{{ step }}</li>
        </ol>
        <RouterLink :to="`/learn/${method.learnSlug}`" class="learn">Why this works →</RouterLink>

        <div class="divider" />

        <h2>{{ method.prompts.before }}</h2>
        <div class="scale" role="radiogroup" aria-label="How do you feel right now?">
          <button
            v-for="(w, i) in SCALE" :key="w" role="radio" :aria-checked="beforeRating === i + 1"
            class="scale-step dmt-chip" :class="{ 'dmt-chip--on': beforeRating === i + 1 }" @click="beforeRating = i + 1"
          >{{ w }}</button>
        </div>
        <textarea v-model="beforeText" rows="2" maxlength="600" placeholder="a few words, if you like…" class="field dmt-input" />
        <p v-if="beforeReading" class="reflection small">{{ beforeReading.reflection }}</p>
        <button class="dmt-btn dmt-btn--prism" :disabled="starting" @click="start">Begin {{ method.name.toLowerCase() }}</button>
      </section>
    </template>

    <!-- ── The thread ── -->
    <section class="panel dmt-card">
      <p class="dmt-eyebrow">Your thread · last 14 days</p>
      <div class="thread" :aria-label="`${threadDays} of the last 14 days practiced`">
        <span v-for="(d, i) in thread" :key="i" class="knot" :class="{ 'knot--on dmt-jewel': d, 'knot--today': i === thread.length - 1 }" />
      </div>
      <p v-if="overallShift !== null" class="muted small">
        Average shift across {{ entries.filter(e => e.after).length }} reflected sessions:
        <strong>{{ signed(overallShift) }}</strong> on the five-step scale.
      </p>
      <ul v-if="observations.length" class="notice">
        <li v-for="o in observations" :key="o">{{ o }}</li>
      </ul>
      <p v-else-if="!entries.length" class="muted small">Nothing to notice yet. The thread starts with one session.</p>

      <ul v-if="recent.length" class="recent">
        <li v-for="e in recent" :key="e.id">
          <span>{{ METHODS[e.method].name }}</span>
          <span class="muted">{{ fmtDay(e.startedAt) }}</span>
          <span v-if="e.after">{{ SCALE[e.before.rating - 1] }} → {{ SCALE[e.after.rating - 1] }}</span>
          <span v-if="e.after?.reading" class="tone tone--inline">{{ e.after.reading.tone }}</span>
        </li>
      </ul>
    </section>

    <label class="privacy">
      <input type="checkbox" :checked="localOnly" @change="setLocalOnly(($event.target as HTMLInputElement).checked)" />
      <span>
        Read my answers on this device only.
        <span class="muted">When this is off, your words are sent once to a free AI model to write the reflection. ChannelZero doesn’t keep them; the session record stays on this device.</span>
      </span>
    </label>
  </div>
  </div>
</template>

<style scoped>
/* Look comes from src/styles/dmt.css; this is layout and type scale only. */
.practice-root { min-height: 100vh; }
.practice {
  max-width: 640px;
  margin: 0 auto;
  padding: 40px 16px 120px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.head h1 { font-size: 28px; font-weight: 200; letter-spacing: 0.32em; text-transform: uppercase; }
.head p { margin-top: 8px; font-size: 13px; color: var(--dmt-ink-dim); }

.panel { padding: 20px; display: flex; flex-direction: column; gap: 12px; }
h2 { font-size: 17px; font-weight: 300; color: var(--dmt-ink); }
.what { font-size: 14.5px; line-height: 1.6; font-weight: 300; }
.muted { color: var(--dmt-ink-faint); }
.small { font-size: 12px; line-height: 1.55; }

.methods { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.method {
  text-align: left;
  padding: 12px 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}
.method-name { font-size: 13px; color: var(--dmt-ink); }
.method-meta { font-size: 10.5px; color: var(--dmt-ink-faint); }
.method-bar { height: 2px; border-radius: 2px; background: rgba(190, 160, 255, 0.12); overflow: hidden; margin-top: 5px; }
.method-bar span { display: block; height: 100%; background: var(--dmt-prism-linear); }
.method-tag { font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--dmt-lime); }

.how { padding-left: 18px; font-size: 13px; line-height: 1.65; color: var(--dmt-ink-dim); list-style: decimal; }
.how li::marker { color: var(--dmt-cyan); }
.learn { font-size: 12px; color: var(--dmt-cyan); }
.divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(190, 160, 255, 0.3), transparent); margin: 4px 0; }

.scale { display: flex; gap: 6px; flex-wrap: wrap; }
.scale-step { flex: 1 1 0; min-width: 64px; padding: 9px 4px; font-size: 11.5px; cursor: pointer; }

.field { width: 100%; resize: vertical; padding: 9px 11px; font-size: 13px; }

.row { display: flex; gap: 8px; flex-wrap: wrap; }
.dmt-btn { align-self: flex-start; }
.btn--ghost { border-color: transparent; background: transparent; color: var(--dmt-ink-faint); }

.shift { font-size: 17px; font-weight: 300; }
.reflection { font-size: 14px; line-height: 1.6; font-weight: 300; color: var(--dmt-ink); }
.tone {
  display: block;
  font-size: 9px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--dmt-magenta);
  margin-bottom: 3px;
}
.tone--inline { display: inline; margin-left: 6px; }
.during { font-size: 12.5px; line-height: 1.6; display: flex; flex-direction: column; gap: 3px; }

.thread { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.knot { width: 11px; height: 11px; border-radius: 50%; border: 1px solid rgba(190, 160, 255, 0.22); }
.knot--on { border-color: transparent; }
.knot--today { outline: 1px solid rgba(46, 230, 255, 0.5); outline-offset: 3px; }
.notice { font-size: 13.5px; line-height: 1.6; font-weight: 300; display: flex; flex-direction: column; gap: 5px; }
.notice li::before { content: '✧ '; color: var(--dmt-cyan); }
.recent { font-size: 12px; display: flex; flex-direction: column; gap: 6px; margin-top: 4px; color: var(--dmt-ink-dim); }
.recent li { display: flex; gap: 10px; flex-wrap: wrap; }

.privacy { display: flex; gap: 10px; font-size: 12px; line-height: 1.5; align-items: flex-start; padding: 0 4px; color: var(--dmt-ink-dim); }
.privacy input { margin-top: 3px; accent-color: var(--dmt-violet); }
</style>
