/**
 * Site section registry for the admin Sections view.
 *
 * `events` lists the analytics events the section's code actually emits via
 * logEvent (grep `logEvent(` to verify). Keep it in sync when instrumenting a
 * view; the admin view flags sections whose events the server would reject
 * and server events no section emits.
 */

export type Pillar = 'expression' | 'hypnosis' | 'ritual' | 'mirror' | 'onboarding' | 'other'
export type ExperimentId = 'E1' | 'E2' | 'E3'

export interface SiteSection {
  id: string
  name: string
  route: string          // route as declared in the router
  preview: string        // concrete URL to load in the preview frame
  pillar: Pillar
  auth: boolean          // requiresAuth: logEvent is a no-op for anonymous visitors
  experiments: ExperimentId[]
  events: string[]
  note?: string
}

export const PILLAR_LABELS: Record<Pillar, string> = {
  expression: 'Self-expression',
  hypnosis:   'Hypnosis / entrainment',
  ritual:     'Routine / ritual',
  mirror:     'OAuth mirror',
  onboarding: 'Onboarding',
  other:      'Other / experiments',
}

export const EXPERIMENT_LABELS: Record<ExperimentId, string> = {
  E1: 'Ritual loop',
  E2: 'Mirror',
  E3: 'Open hypnosis toy',
}

export const SITE_SECTIONS: SiteSection[] = [
  // Ritual
  { id: 'home',     name: 'Home hub',          route: '/',        preview: '/',        pillar: 'ritual', auth: false, experiments: ['E1'], events: [],
    note: "Today's Practice card routes archetypes to sessions" },
  { id: 'checkin',  name: 'Daily check-in',    route: '/checkin', preview: '/checkin', pillar: 'ritual', auth: true,  experiments: ['E1'],
    events: ['checkin_started', 'checkin_completed', 'practice_started'] },

  // Self-expression
  { id: 'journal',  name: 'Journal',           route: '/journal', preview: '/journal', pillar: 'expression', auth: true,  experiments: [],
    events: ['journal_session_started', 'journal_session_completed'], note: 'Entries are local-only; only events reach the server' },
  { id: 'studio',   name: 'Glass studio',      route: '/studio',  preview: '/studio',  pillar: 'expression', auth: false, experiments: [], events: [] },
  { id: 'reader',   name: 'Speed reader',      route: '/reader',  preview: '/reader',  pillar: 'expression', auth: false, experiments: [], events: [] },

  // Hypnosis
  { id: 'zeromind', name: 'Zeromind trance',   route: '/zeromind', preview: '/zeromind', pillar: 'hypnosis', auth: false, experiments: ['E1', 'E3'],
    events: ['zeromind_session_started', 'zeromind_session_completed'] },
  { id: 'spiral',   name: 'Spiral',            route: '/spiral',   preview: '/spiral',   pillar: 'hypnosis', auth: false, experiments: ['E1', 'E3'], events: [],
    note: 'Writes the local practice log only; no server event, so no streak credit' },
  { id: 'audio',    name: 'Audio journey',     route: '/audio',    preview: '/audio',    pillar: 'hypnosis', auth: false, experiments: ['E1', 'E3'], events: [],
    note: 'Writes the local practice log only; no server event' },
  { id: 'trance',   name: 'Trance',            route: '/trance',   preview: '/trance',   pillar: 'hypnosis', auth: false, experiments: ['E1', 'E3'], events: [] },
  { id: 'hypno',    name: 'Hypno visual',      route: '/hypno',    preview: '/hypno',    pillar: 'hypnosis', auth: false, experiments: ['E3'], events: [] },
  { id: 'webaudio', name: 'Star tunnel breath', route: '/webaudio', preview: '/webaudio', pillar: 'hypnosis', auth: false, experiments: ['E1', 'E3'], events: [] },

  // Mirror
  { id: 'calibrate', name: 'Connectors',       route: '/calibrate', preview: '/calibrate', pillar: 'mirror', auth: true, experiments: ['E2'],
    events: ['connected_any', 'connected_2plus'] },
  { id: 'reading',  name: 'Connector reading', route: '/calibrate/:provider', preview: '/calibrate/spotify', pillar: 'mirror', auth: true, experiments: ['E2'], events: [] },
  { id: 'portrait', name: 'Integrated portrait', route: '/portrait', preview: '/portrait', pillar: 'mirror', auth: true, experiments: ['E2'],
    events: ['portrait_viewed', 'portrait_generated'] },
  { id: 'psychoanalysis', name: 'Psychoanalysis', route: '/psychoanalysis', preview: '/psychoanalysis', pillar: 'mirror', auth: true, experiments: [], events: [] },
  { id: 'intake',   name: 'Confessional intake', route: '/intake', preview: '/intake', pillar: 'mirror', auth: true, experiments: [],
    events: ['has_vibe_vector'] },

  // Onboarding
  { id: 'poll',       name: 'Archetype poll', route: '/poll',       preview: '/poll',       pillar: 'onboarding', auth: false, experiments: [], events: [] },
  { id: 'onboarding', name: 'Onboarding',     route: '/onboarding', preview: '/onboarding', pillar: 'onboarding', auth: true,  experiments: [], events: [] },
  { id: 'discovery',  name: 'Discovery',      route: '/discovery',  preview: '/discovery',  pillar: 'onboarding', auth: true,  experiments: [], events: [] },
  { id: 'learn',      name: 'Learn',          route: '/learn',      preview: '/learn',      pillar: 'onboarding', auth: false, experiments: [], events: [] },

  // Other
  { id: 'universe',    name: 'Signal universe', route: '/universe',    preview: '/universe',    pillar: 'other', auth: true,  experiments: [], events: [] },
  { id: 'liquidglass', name: 'Liquid glass',    route: '/liquidglass', preview: '/liquidglass', pillar: 'other', auth: false, experiments: [], events: [] },
  { id: 'sessions',    name: 'Sessions',        route: '/sessions',    preview: '/sessions',    pillar: 'other', auth: false, experiments: [], events: [] },
]

/** Routes with visuals worth a flash-safety scan. */
export const VISUAL_SECTION_IDS = ['spiral', 'hypno', 'trance', 'zeromind', 'webaudio', 'audio', 'studio', 'liquidglass']
