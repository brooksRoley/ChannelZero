import { ref, computed } from 'vue'
import { chunkPhrases, splitWords, SENTENCE_HOLD, type Phrase } from '@/story/phrases'

// Shared state — module-level so it persists across all consumers
const storyText = ref(``)
const currentIndex = ref(0)
const isPlaying = ref(false)

// Background media state
const backgroundMedia = ref<string | null>(null)
const isBackgroundVideo = ref(false)

const wpm = ref(250)

// ── Phrase mode ──────────────────────────────────────────────────
// When enabled, words are grouped into short readable chunks.
// tranceSynced locks the interval to 2.4 Hz (binaural baseline).
const phraseMode = ref(true)
const tranceSynced = ref(false)
const TRANCE_PHRASE_MS = Math.round(1000 / 2.4) // 417 ms @ 2.4 Hz

const words = computed(() => splitWords(storyText.value))
const currentWord = computed(() => words.value[currentIndex.value] || '')
const progress = computed(() =>
  words.value.length > 0 ? ((currentIndex.value + 1) / words.value.length) * 100 : 0
)

// Chunk words into 2–3 word phrases, breaking at punctuation boundaries
const phrases = computed<Phrase[]>(() => chunkPhrases(words.value))

// Which phrase contains currentIndex
const currentPhraseIndex = computed(() => {
  const idx = currentIndex.value
  const ps = phrases.value
  for (let i = ps.length - 1; i >= 0; i--) {
    if (idx >= ps[i].startIdx) return i
  }
  return 0
})

const currentPhrase = computed(() => phrases.value[currentPhraseIndex.value]?.text ?? '')

// ── Playback engine (recursive setTimeout for variable phrase timing) ──
let timeoutId: number | null = null

function getMs(): number {
  if (phraseMode.value && tranceSynced.value) return TRANCE_PHRASE_MS
  if (phraseMode.value) {
    const ph = phrases.value[currentPhraseIndex.value]
    const wordCount = ph ? ph.endIdx - ph.startIdx + 1 : 1
    return Math.round((60000 / wpm.value) * wordCount)
  }
  return Math.round(60000 / wpm.value)
}

function tick() {
  if (!isPlaying.value) return

  if (phraseMode.value) {
    const nextIdx = currentPhraseIndex.value + 1
    if (nextIdx < phrases.value.length) {
      currentIndex.value = phrases.value[nextIdx].startIdx
    } else {
      currentIndex.value = 0
    }
  } else {
    if (currentIndex.value < words.value.length - 1) {
      currentIndex.value++
    } else {
      currentIndex.value = 0
    }
  }

  schedule()
}

function schedule() {
  if (timeoutId) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
  if (!isPlaying.value) return
  const ph = phrases.value[currentPhraseIndex.value]
  // Add an extra beat at sentence endings for natural breath
  const ms = phraseMode.value && ph?.isPausePoint ? Math.round(getMs() * SENTENCE_HOLD) : getMs()
  timeoutId = window.setTimeout(tick, ms)
}

function play() {
  if (currentIndex.value >= words.value.length - 1) currentIndex.value = 0
  isPlaying.value = true
  schedule()
}

function pause() {
  isPlaying.value = false
  if (timeoutId) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
}

function reset() {
  pause()
  currentIndex.value = 0
}

function seekToWord(index: number) {
  const wasPlaying = isPlaying.value
  if (wasPlaying) pause()
  currentIndex.value = index
  if (wasPlaying) play()
}

function setStoryText(text: string) {
  pause()
  currentIndex.value = 0
  storyText.value = text
}

function setPhraseMode(enabled: boolean) {
  phraseMode.value = enabled
  if (!enabled) tranceSynced.value = false
  if (isPlaying.value) {
    pause()
    play()
  }
}

function setTranceSynced(synced: boolean) {
  tranceSynced.value = synced
  if (synced) phraseMode.value = true
  if (isPlaying.value) {
    pause()
    play()
  }
}

function clearStoryText() {
  setStoryText('')
}

function setBackgroundMedia(url: string, video: boolean) {
  if (backgroundMedia.value) {
    URL.revokeObjectURL(backgroundMedia.value)
  }
  backgroundMedia.value = url
  isBackgroundVideo.value = video
}

function clearBackgroundMedia() {
  if (backgroundMedia.value) {
    URL.revokeObjectURL(backgroundMedia.value)
    backgroundMedia.value = null
    isBackgroundVideo.value = false
  }
}

function setWpm(value: number) {
  wpm.value = value
  if (isPlaying.value) {
    pause()
    play()
  }
}

export function useStoryStore() {
  return {
    storyText,
    words,
    currentWord,
    currentPhrase,
    currentPhraseIndex,
    phrases,
    currentIndex,
    progress,
    isPlaying,
    wpm,
    phraseMode,
    tranceSynced,
    setStoryText,
    clearStoryText,
    play,
    pause,
    reset,
    seekToWord,
    setWpm,
    setPhraseMode,
    setTranceSynced,
    backgroundMedia,
    isBackgroundVideo,
    setBackgroundMedia,
    clearBackgroundMedia
  }
}
