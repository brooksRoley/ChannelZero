import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { ref } from 'vue'

const phase = ref('idle')
const sessionActive = ref(true)
const tunnelPulseStrength = ref(0)
vi.mock('tone', () => ({}))
vi.mock('@/composables/useTranceEngine', () => ({
  useTranceEngine: () => ({ phase, sessionActive, tunnelPulseStrength }),
}))

import PracticeCompanion from '@/components/PracticeCompanion.vue'
import { usePracticeJourney } from '@/composables/usePracticeJourney'

describe('PracticeCompanion', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  })

  it('asks at a deeper phase change and mirrors the answer', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/practice', '/zeromind'].map((path) => ({ path, component: { template: '<div />' } })),
    })
    usePracticeJourney().begin('zeromind', { rating: 2 })
    await router.push('/zeromind')
    const w = mount(PracticeCompanion, { global: { plugins: [router] } })
    expect(w.text()).toContain('Breath descent')

    phase.value = 'deepen'
    await flushPromises()
    expect(w.text()).toContain('What do you notice in your body right now?')

    await w.find('input').setValue('heavy and calm')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('settling')
    expect(usePracticeJourney().pending.value?.during[0].text).toBe('heavy and calm')
    expect(tunnelPulseStrength.value).toBeGreaterThan(0)
  })

  it('stays quiet at phase changes in fractionation, which speaks its own lines', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/practice', '/fractionation'].map((path) => ({ path, component: { template: '<div />' } })),
    })
    phase.value = 'idle'
    usePracticeJourney().begin('fractionation', { rating: 2 })
    await router.push('/fractionation')
    const w = mount(PracticeCompanion, { global: { plugins: [router] } })
    expect(w.text()).toContain('Fractionation')

    phase.value = 'deepen'
    await flushPromises()
    expect(w.find('form').exists()).toBe(false)
    expect(w.text()).toContain('note')
  })
})
