// Phrase chunking shared by the reader (useStoryStore) and the story timeline.
// PURE and dependency-free so the reader doesn't pull in audio code.

export interface Phrase {
  text: string
  startIdx: number
  endIdx: number
  isPausePoint: boolean // sentence-ending punctuation → extra hold
}

/** Extra hold on a sentence-ending phrase, as a multiple of its read time. */
export const SENTENCE_HOLD = 1.45

/** Chunk words into 2–3 word phrases, breaking at punctuation boundaries. */
export function chunkPhrases(ws: string[]): Phrase[] {
  const result: Phrase[] = []
  let start = 0
  let count = 0
  for (let i = 0; i < ws.length; i++) {
    count++
    const word = ws[i]
    const isSentenceEnd = /[.!?]['"]?$/.test(word)
    const isClauseEnd = /[,;:—…]['"]?$/.test(word) && count >= 2
    if (isSentenceEnd || isClauseEnd || count >= 3 || i === ws.length - 1) {
      result.push({
        text: ws.slice(start, i + 1).join(' '),
        startIdx: start,
        endIdx: i,
        isPausePoint: isSentenceEnd,
      })
      start = i + 1
      count = 0
    }
  }
  return result
}

export function splitWords(text: string): string[] {
  return text.split(/\s+/).filter((w) => w.length > 0)
}
