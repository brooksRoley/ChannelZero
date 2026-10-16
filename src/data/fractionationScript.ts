// Spoken lines for the fractionation session (read by useFractionation).
// Plain, calm, second person. Per-round arrays are indexed by round − 1;
// if a session runs more rounds than there are lines, the last line repeats.

export const FRACTIONATION_SCRIPT = {
  induction: [
    'Find a comfortable position, and let your hands rest.',
    'Take a slow breath in… and let it go.',
    'Let your attention settle on the sound around you.',
    'There is nothing you need to do right now.',
  ],
  descend: 'When you are ready, let your eyes close.',
  deepen: [
    'Good. Just notice how heavy your body feels.',
    'Each breath lets you settle a little further.',
    'Deeper still. Nothing to hold on to now.',
  ],
  emerge: [
    'In a moment, let your eyes open… and come up just a little, noticing the room.',
    'Let your eyes open again… just enough to see the light.',
    'Open your eyes for a moment… and notice how calm you feel.',
  ],
  reinduce: [
    'And close them now… letting yourself go twice as deep.',
    'Close them again… and drop down twice as deep as before.',
    'And close them… sinking further than last time.',
  ],
  final: 'Rest here for a while. Just breathe, and enjoy the stillness.',
  wake: [
    'In a moment I will count from one to three.',
    'One… feeling returning to your hands and feet.',
    'Two… taking a fuller breath.',
    'Three… eyes open, refreshed.',
  ],
} as const

export type FractionationScript = typeof FRACTIONATION_SCRIPT

/** Pick a per-round line, repeating the last one past the end. */
export function lineForRound(lines: readonly string[], round: number): string {
  return lines[Math.min(Math.max(round - 1, 0), lines.length - 1)]
}
