import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, reactive } from 'vue'

vi.mock('tone', () => ({}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))
vi.mock('@/composables/useTranceEngine', () => ({
  BINAURAL_LAYERS: {
    alpha: { id: 'alpha', label: 'Alpha Wave', leftHz: 195, rightHz: 205, targetBand: 'alpha' },
  },
  useTranceEngine: () => ({}),
}))
vi.mock('@/composables/useStudioBinaural', () => ({
  BANDS: { gamma: { beatHz: 40, carrierHz: 220 } },
}))

const errors = reactive<Record<string, string>>({})
vi.mock('@/composables/useAdminStore', () => ({
  useAdminStore: () => ({
    eventStats: ref([
      { event: 'checkin_completed', total: 4, users: 1, last_7d: 2, last_at: new Date().toISOString() },
    ]),
    validEvents: ref(['checkin_started', 'checkin_completed', 'portrait_viewed']),
    errors,
  }),
}))

import AdminSections from '@/components/admin/AdminSections.vue'
import AdminHypnoAudit from '@/components/admin/AdminHypnoAudit.vue'

describe('AdminSections', () => {
  it('renders sections and flags events the server would reject', () => {
    const w = mount(AdminSections)
    expect(w.text()).toContain('Daily check-in')
    // practice_started is emitted by the check-in section but absent from validEvents here
    expect(w.text()).toContain('rejected by the server')
    expect(w.text()).toContain('practice_started')
    // portrait_viewed is allowed but no section emits it
    expect(w.text()).toContain('portrait_viewed')
  })

  it('shows a panel error without hiding the rest', () => {
    errors.events = 'Failed to fetch'
    const w = mount(AdminSections)
    expect(w.find('[role="alert"]').text()).toContain('Failed to fetch')
    expect(w.text()).toContain('Daily check-in')
    delete errors.events
  })
})

describe('AdminHypnoAudit', () => {
  it('renders the spec audit with a gamma warning', () => {
    const w = mount(AdminHypnoAudit)
    expect(w.text()).toContain('Binaural spec audit')
    expect(w.text()).toContain('Alpha Wave')
    expect(w.text()).toContain('weakly perceived')
  })
})
