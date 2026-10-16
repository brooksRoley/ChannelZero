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
  <div class="practice">
    <header class="head">
      <h1>Practice</h1>
      <p>Learn a method, try it, and notice what changes. Everything here stays on this device.</p>
    </header>

    <!-- ── Finished: the mirror ── -->
    <section v-if="finished" class="panel panel--glow">
      <p class="eyebrow">{{ METHODS[finished.method].name }} · done</p>
      <p class="shift">{{ shiftLine }}</p>
      <p v-if="afterReading" class="reflection">
        <span class="tone">{{ afterReading.tone }}</span>{{ afterReading.reflection }}
      </p>
      <ul v-if="finished.during.length" class="during">
        <li v-for="(n, i) in finished.during" :key="i">
          <span class="muted">{{ n.prompt }}</span> {{ n.text }} <span class="tone tone--inline">{{ n.tone }}</span>
        </li>
      </ul>
      <button class="btn" @click="startAnother">Back to practice</button>
    </section>

    <!-- ── A session is open: after-check ── -->
    <section v-else-if="pending && pendingMethod" class="panel panel--glow">
      <p class="eyebrow">{{ pendingMethod.name }} · {{ pending.sessionEndedAt ? 'finished' : 'in progress' }}</p>
      <template v-if="pending.sessionEndedAt">
        <h2>{{ pendingMethod.prompts.after }}</h2>
        <div class="scale" role="radiogroup" aria-label="How do you feel now?">
          <button
            v-for="(w, i) in SCALE" :key="w" role="radio" :aria-checked="afterRating === i + 1"
            class="scale-step" :class="{ 'scale-step--on': afterRating === i + 1 }" @click="afterRating = i + 1"
          >{{ w }}</button>
        </div>
        <p class="muted small">You started at “{{ SCALE[pending.before.rating - 1] }}”.</p>
        <textarea v-model="afterText" rows="2" maxlength="600" placeholder="a few words, if you like…" class="field" />
        <button class="btn btn--primary" :disabled="finishing" @click="complete">
          {{ finishing ? 'Reading…' : 'Close the session' }}
        </button>
      </template>
      <template v-else>
        <p class="muted">Your session is still open.</p>
        <div class="row">
          <button class="btn btn--primary" @click="router.push(pendingMethod.route)">Return to it</button>
          <button class="btn" @click="markEnded">I finished it</button>
          <button class="btn btn--ghost" @click="abandon">Let it go</button>
        </div>
      </template>
    </section>

    <!-- ── Choose + learn + before-check ── -->
    <template v-else>
      <section class="methods" aria-label="Methods">
        <button
          v-for="id in METHOD_ORDER" :key="id"
          class="method" :class="{ 'method--on': chosen === id }" @click="chosen = id"
        >
          <span class="method-name">{{ METHODS[id].name }}</span>
          <span class="method-meta">{{ familiarityByMethod[id].label }} · {{ METHODS[id].minutes }} min</span>
          <span class="method-bar"><span :style="{ width: `${familiarityByMethod[id].progress * 100}%` }" /></span>
          <span v-if="id === suggested" class="method-tag">suggested now</span>
        </button>
      </section>

      <section class="panel">
        <p class="eyebrow">{{ method.name }}<span v-if="method.needsHeadphones"> · headphones</span></p>
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
            class="scale-step" :class="{ 'scale-step--on': beforeRating === i + 1 }" @click="beforeRating = i + 1"
          >{{ w }}</button>
        </div>
        <textarea v-model="beforeText" rows="2" maxlength="600" placeholder="a few words, if you like…" class="field" />
        <p v-if="beforeReading" class="reflection small">{{ beforeReading.reflection }}</p>
        <button class="btn btn--primary" :disabled="starting" @click="start">Begin {{ method.name.toLowerCase() }}</button>
      </section>
    </template>

    <!-- ── The thread ── -->
    <section class="panel">
      <p class="eyebrow">Your thread · last 14 days</p>
      <div class="thread" :aria-label="`${threadDays} of the last 14 days practiced`">
        <span v-for="(d, i) in thread" :key="i" class="knot" :class="{ 'knot--on': d, 'knot--today': i === thread.length - 1 }" />
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
</template>

<style scoped>
.practice {
  max-width: 640px;
  margin: 0 auto;
  padding: 32px 16px 120px;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.head h1 { font-size: 22px; font-weight: 300; letter-spacing: 0.2em; text-transform: uppercase; }
.head p { margin-top: 6px; font-size: 13px; color: rgba(226, 232, 240, 0.5); }

.panel {
  padding: 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.panel--glow { border-color: rgba(167, 139, 250, 0.25); background: rgba(167, 139, 250, 0.04); }
.eyebrow { font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(167, 139, 250, 0.8); }
h2 { font-size: 16px; font-weight: 300; }
.what { font-size: 14px; line-height: 1.55; font-weight: 300; }
.muted { color: rgba(226, 232, 240, 0.45); }
.small { font-size: 12px; line-height: 1.5; }

.methods { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.method {
  position: relative;
  text-align: left;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: inherit;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.method:hover { border-color: rgba(255, 255, 255, 0.15); }
.method--on { border-color: rgba(167, 139, 250, 0.45); background: rgba(167, 139, 250, 0.06); }
.method-name { font-size: 13px; }
.method-meta { font-size: 10.5px; color: rgba(226, 232, 240, 0.45); }
.method-bar { height: 2px; border-radius: 2px; background: rgba(255, 255, 255, 0.06); overflow: hidden; margin-top: 4px; }
.method-bar span { display: block; height: 100%; background: rgba(167, 139, 250, 0.6); }
.method-tag { font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: rgba(52, 211, 153, 0.8); }

.how { padding-left: 18px; font-size: 13px; line-height: 1.6; color: rgba(226, 232, 240, 0.75); list-style: decimal; }
.learn { font-size: 12px; color: rgba(167, 139, 250, 0.8); }
.divider { height: 1px; background: rgba(255, 255, 255, 0.06); margin: 4px 0; }

.scale { display: flex; gap: 6px; flex-wrap: wrap; }
.scale-step {
  flex: 1 1 0;
  min-width: 64px;
  padding: 8px 4px;
  border-radius: 10px;
  font-size: 11.5px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(226, 232, 240, 0.55);
  cursor: pointer;
}
.scale-step--on { border-color: rgba(167, 139, 250, 0.6); color: #e2e8f0; background: rgba(167, 139, 250, 0.1); }

.field {
  width: 100%;
  resize: vertical;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
  color: #e2e8f0;
  outline: none;
}
.field:focus { border-color: rgba(167, 139, 250, 0.4); }

.row { display: flex; gap: 8px; flex-wrap: wrap; }
.btn {
  align-self: flex-start;
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 0.06em;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(226, 232, 240, 0.8);
  cursor: pointer;
}
.btn:disabled { opacity: 0.4; cursor: default; }
.btn--primary { background: rgba(167, 139, 250, 0.15); border-color: rgba(167, 139, 250, 0.4); color: #ede9fe; }
.btn--ghost { border-color: transparent; color: rgba(226, 232, 240, 0.4); }

.shift { font-size: 16px; font-weight: 300; }
.reflection { font-size: 13.5px; line-height: 1.55; font-weight: 300; color: rgba(226, 232, 240, 0.85); }
.tone {
  display: block;
  font-size: 9px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(167, 139, 250, 0.8);
  margin-bottom: 2px;
}
.tone--inline { display: inline; margin-left: 6px; }
.during { font-size: 12.5px; line-height: 1.6; display: flex; flex-direction: column; gap: 2px; }

.thread { display: flex; gap: 6px; align-items: center; }
.knot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid rgba(255, 255, 255, 0.12); }
.knot--on { background: rgba(167, 139, 250, 0.7); border-color: transparent; }
.knot--today { outline: 1px solid rgba(255, 255, 255, 0.25); outline-offset: 2px; }
.notice { font-size: 13px; line-height: 1.6; font-weight: 300; display: flex; flex-direction: column; gap: 4px; }
.recent { font-size: 12px; display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.recent li { display: flex; gap: 10px; flex-wrap: wrap; }

.privacy { display: flex; gap: 10px; font-size: 12px; line-height: 1.5; align-items: flex-start; padding: 0 4px; }
.privacy input { margin-top: 3px; accent-color: #a78bfa; }
</style>
