/**
 * Practice methods — the bridge between Learn (why), the tools (do) and the
 * reflection loop (notice). Each method names its tool route, a three-step
 * how-to, and the plain prompts asked before, during and after.
 */

export type MethodId = 'zeromind' | 'spiral' | 'audio' | 'studio' | 'trance'

export interface PracticeMethod {
  id: MethodId
  name: string
  route: string
  minutes: number
  /** One sentence: what the method actually does. */
  what: string
  /** Three concrete steps, in the order you do them. */
  how: [string, string, string]
  learnSlug: string
  needsHeadphones: boolean
  prompts: {
    before: string
    /** Asked softly during a session (Zeromind asks at phase changes). */
    during: string[]
    after: string
  }
}

export const METHODS: Record<MethodId, PracticeMethod> = {
  zeromind: {
    id: 'zeromind',
    name: 'Breath descent',
    route: '/zeromind',
    minutes: 8,
    what: 'Binaural tones and a paced breath guide you down through settling, breathing and descent.',
    how: [
      'Headphones on, eyes soft, sit or lie so nothing needs holding up.',
      'Press start and let the ring set your breath. Follow it, don’t chase it.',
      'When a question appears, answer in a word or two, or ignore it.',
    ],
    learnSlug: 'binaural-entrainment',
    needsHeadphones: true,
    prompts: {
      before: 'What are you bringing in with you?',
      during: [
        'What do you notice in your body right now?',
        'Where has your attention gone?',
        'One word for this moment?',
      ],
      after: 'What changed, if anything?',
    },
  },
  spiral: {
    id: 'spiral',
    name: 'Fixation spiral',
    route: '/spiral',
    minutes: 5,
    what: 'A single turning point for the eyes. Fixed attention narrows, and the rest of the mind quiets around it.',
    how: [
      'Sit at arm’s length from the screen and let your shoulders drop.',
      'Rest your gaze on the centre. When your eyes want to close, let them.',
      'If thoughts pull you away, return to the centre without scolding yourself.',
    ],
    learnSlug: 'hypnotic-induction',
    needsHeadphones: false,
    prompts: {
      before: 'How scattered does your attention feel?',
      during: ['What pulled your attention away just now?'],
      after: 'Where did your attention settle?',
    },
  },
  audio: {
    id: 'audio',
    name: 'Adaptive journey',
    route: '/audio',
    minutes: 10,
    what: 'Entrainment audio that follows your energy instead of fighting it, then slowly leads it somewhere calmer.',
    how: [
      'Choose a journey that matches how you feel now, not how you want to feel.',
      'Let it play. Move if you need to, and stay with the sound.',
      'Notice the moment the sound starts leading you instead of matching you.',
    ],
    learnSlug: 'brainwave-entrainment-techniques',
    needsHeadphones: true,
    prompts: {
      before: 'What is your energy like right now?',
      during: ['Is the sound matching you or leading you?'],
      after: 'Where did the sound take you?',
    },
  },
  studio: {
    id: 'studio',
    name: 'Subliminal authoring',
    route: '/studio',
    minutes: 15,
    what: 'Write your own suggestions, layer them over media with a beat, and export a session made for you.',
    how: [
      'Pick a recipe, or upload a clip that already calms you.',
      'Write three short lines in the present tense. Keep them true enough to believe.',
      'Play it back once before exporting. Notice which line lands hardest.',
    ],
    learnSlug: 'suggestion-induction',
    needsHeadphones: true,
    prompts: {
      before: 'What do you want to hear said to you?',
      during: ['Which line landed hardest?'],
      after: 'How did it feel to write your own suggestion?',
    },
  },
  trance: {
    id: 'trance',
    name: 'Star tunnel',
    route: '/trance',
    minutes: 6,
    what: 'A breath journey through a field of stars. Each exhale carries you a little further in.',
    how: [
      'Dim the room and make the screen the brightest thing you can see.',
      'Breathe with the tunnel: in as it gathers, out as it opens.',
      'Count ten exhales and lose count. Losing count is the point.',
    ],
    learnSlug: 'trance-states',
    needsHeadphones: false,
    prompts: {
      before: 'How busy is your mind, from 1 to 5?',
      during: ['How far in do you feel?'],
      after: 'What was it like to lose count?',
    },
  },
}

export const METHOD_ORDER: MethodId[] = ['zeromind', 'spiral', 'trance', 'audio', 'studio']

/** Practice-log session id → method (the log predates methods). */
export const SESSION_TO_METHOD: Record<string, MethodId> = {
  zeromind: 'zeromind',
  spiral: 'spiral',
  audio: 'audio',
}
