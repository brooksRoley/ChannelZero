<template>
  <div class="ccard-idle border rounded-2xl p-6 shadow-xl" data-testid="instagram-import">
    <div class="mb-4">
      <h2 class="text-2xl font-bold text-pink-400">Instagram</h2>
      <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">Your data export, on this device</h3>
    </div>

    <p class="text-sm text-gray-400">{{ RETIRED_PROVIDERS.instagram }}</p>
    <p class="mt-2 text-sm text-gray-400">
      Only when you liked, commented, saved and posted is kept: counts per day and hour.
      No usernames, links, captions or comment text. Nothing is uploaded, and none of it reaches the Oracle or any AI.
    </p>

    <details class="mt-3 text-xs text-gray-500">
      <summary class="cursor-pointer text-gray-400">How to get your export</summary>
      <ol class="mt-2 list-decimal ml-4 space-y-1">
        <li>Instagram → Settings → Accounts Center → Your information and permissions → Download your information.</li>
        <li>Choose "Some of your information": likes, comments, saved, and your content.</li>
        <li>Format <strong>JSON</strong> (not HTML), download to your device, and unzip it.</li>
        <li>Choose the unzipped folder below.</li>
      </ol>
    </details>

    <label class="mt-4 inline-block text-xs text-pink-300 hover:underline cursor-pointer">
      {{ activity ? 'Import a newer export' : 'Choose the export folder' }}
      <input type="file" class="sr-only" webkitdirectory multiple data-testid="instagram-folder" @change="onPick" />
    </label>
    <span v-if="busy" class="ml-3 text-xs text-gray-500">Reading…</span>

    <p v-if="note" class="mt-3 text-xs text-amber-300" data-testid="instagram-note">{{ note }}</p>

    <div v-if="activity && activity.days.length" class="mt-4 space-y-3 text-sm text-gray-300" data-testid="instagram-summary">
      <p>
        Last 30 days: {{ line(month) }}.
        <span v-if="busiest !== null" class="text-gray-500">Busiest hour {{ hourLabel(busiest) }}.</span>
      </p>
      <ul class="space-y-1">
        <li v-for="d in activity.days.slice(0, 7)" :key="d.date">
          <span class="text-gray-500">{{ dayLabel(d.date) }}</span> · {{ line(d) }}
        </li>
      </ul>
    </div>

    <details v-if="activity" class="mt-3 text-xs text-gray-500" data-testid="instagram-files">
      <summary class="cursor-pointer">Files read ({{ activity.files.length }}; {{ activity.skipped }} others skipped)</summary>
      <ul class="mt-2 space-y-0.5 font-mono">
        <li v-for="f in activity.files" :key="f.path">{{ shortPath(f.path) }}: {{ f.dated }} of {{ f.records }} dated</li>
      </ul>
    </details>

    <button v-if="activity" class="mt-4 text-xs text-gray-500 hover:underline" @click="forget">Forget this import</button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RETIRED_PROVIDERS } from '@/config/connectorConfig'
import {
  KINDS, clearActivity, loadActivity, parseExport, saveActivity, totals,
  type ActivityKind, type ExportFile, type InstagramActivity,
} from '@/composables/instagramExport'

const activity = ref<InstagramActivity | null>(loadActivity())
const busy = ref(false)
const note = ref('')

const WORDS: Record<ActivityKind, [string, string]> = {
  like: ['like', 'likes'], comment: ['comment', 'comments'], save: ['save', 'saves'],
  post: ['post', 'posts'], story: ['story', 'stories'],
}

const month = computed(() => (activity.value ? totals(activity.value, 30) : null))
const busiest = computed(() => {
  const h = activity.value?.hours ?? []
  const max = Math.max(0, ...h)
  return max ? h.indexOf(max) : null
})

function line(counts: Record<ActivityKind, number> | null): string {
  if (!counts) return ''
  const parts = KINDS.filter((k) => counts[k]).map((k) => `${counts[k]} ${WORDS[k][counts[k] === 1 ? 0 : 1]}`)
  return parts.length ? parts.join(', ') : 'nothing'
}

function hourLabel(h: number): string {
  return new Date(2000, 0, 1, h).toLocaleTimeString(undefined, { hour: 'numeric' })
}

function dayLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function shortPath(p: string): string {
  return p.split('/').slice(-2).join('/')
}

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  input.value = ''
  if (!picked.length) return
  busy.value = true
  note.value = ''
  try {
    const files: ExportFile[] = []
    for (const f of picked) {
      const path = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
      // Only JSON is read; photos and videos in the export are never opened.
      files.push({ path, text: path.toLowerCase().endsWith('.json') ? await f.text() : '' })
    }
    const parsed = parseExport(files)
    if (parsed.htmlOnly) {
      note.value = 'This export is HTML. Request it again with Format: JSON.'
    } else if (!parsed.files.length) {
      note.value = "No likes, comments, saves or posts in this folder. Choose the export's top folder."
    } else if (!parsed.files.some((f) => f.dated)) {
      note.value = "Found the activity files but couldn't read any dates. The export format may have changed."
    }
    if (parsed.files.length) {
      activity.value = parsed
      saveActivity(parsed)
    }
  } finally {
    busy.value = false
  }
}

function forget() {
  clearActivity()
  activity.value = null
  note.value = ''
}
</script>
