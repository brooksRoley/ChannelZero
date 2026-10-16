import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('tone', () => ({}))
vi.mock('@/composables/useTranceEngine', async () => {
  const { ref } = await import('vue')
  return { useTranceEngine: () => ({ phase: ref('idle'), sessionActive: ref(false), tunnelPulseStrength: ref(0) }) }
})

import PracticeView from '@/views/PracticeView.vue'
import { usePracticeLog } from '@/composables/usePracticeLog'
import { usePracticeJourney } from '@/composables/usePracticeJourney'

function makeRouter() {
  const stub = { template: '<div />' }
  return createRouter({
    history: createMemoryHistory(),
    routes: ['/practice', '/zeromind', '/spiral', '/audio', '/studio', '/trance', '/learn/:slug']
      .map((path) => ({ path, component: stub })),
  })
}

describe('PracticeView loop', () => {
  beforeEach(() => {
    localStorage.clear()
    usePracticeJourney().abandon()
    // No backend in tests: the reflect call fails and the local read stands.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  })

  it('begins a method, closes on the tool reporting in, and mirrors the shift', async () => {
    const router = makeRouter()
    await router.push('/practice?method=zeromind')
    const w = mount(PracticeView, { global: { plugins: [router] } })

    expect(w.text()).toContain('Breath descent')
    expect(w.text()).toContain('Why this works')

    // Before: "uneasy" (2) + a few words
    await w.findAll('.scale-step')[1].trigger('click')
    await w.find('textarea').setValue('anxious and busy')
    await w.find('.btn--primary').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/zeromind')
    expect(usePracticeJourney().pending.value?.before.rating).toBe(2)

    // The tool logs completion → the open session is marked finished.
    usePracticeLog().logPractice('zeromind', 480_000)
    await flushPromises()
    expect(usePracticeJourney().pending.value?.sessionEndedAt).toBeTruthy()

    await router.push('/practice')
    const w2 = mount(PracticeView, { global: { plugins: [router] } })
    expect(w2.text()).toContain('What changed, if anything?')
    await w2.findAll('.scale-step')[4].trigger('click')
    await w2.find('textarea').setValue('calm and soft')
    await w2.find('.btn--primary').trigger('click')
    await flushPromises()

    expect(w2.text()).toContain('You came in uneasy and left open.')
    expect(w2.text()).toContain('settling')
    expect(usePracticeJourney().entries.value[0].after?.rating).toBe(5)
  })
})
