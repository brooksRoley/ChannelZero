import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MovementShortcut from '@/components/MovementShortcut.vue'

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }))
vi.mock('@/composables/useAuthStore', () => ({ useAuthStore: () => ({ apiFetch }) }))

function routes(map: Record<string, unknown>) {
  apiFetch.mockImplementation((path: string) => Promise.resolve(map[String(path).split('?')[0]]))
}

describe('MovementShortcut', () => {
  beforeEach(() => apiFetch.mockReset())

  it('says nothing is set up when there is no token', async () => {
    routes({ '/api/movement/status': { has_token: false, last_received_at: null }, '/api/movement/days': { days: [] } })
    const w = mount(MovementShortcut)
    await flushPromises()
    expect(w.find('[data-testid="movement-status"]').text()).toBe('No Shortcut set up yet.')
    expect(w.text()).toContain('Make a token')
    expect(w.text()).not.toContain('Delete my movement data')
  })

  it('lists minutes per day with their kinds, on the local date', async () => {
    routes({
      '/api/movement/status': { has_token: true, last_received_at: '2026-10-30T15:00:00Z' },
      '/api/movement/days': { days: [{ date: '2026-10-30', minutes: 62, kinds: [{ kind: 'Running', minutes: 42 }, { kind: 'Walking', minutes: 20 }] }] },
    })
    const w = mount(MovementShortcut)
    await flushPromises()
    const day = w.find('[data-testid="movement-days"]').text()
    expect(day).toContain('Oct 30')
    expect(day).toContain('62 min')
    expect(day).toContain('Running, Walking')
  })

  it('shows a new token once', async () => {
    routes({
      '/api/movement/status': { has_token: false, last_received_at: null },
      '/api/movement/days': { days: [] },
      '/api/movement/token': { token: 'tok-123' },
    })
    const w = mount(MovementShortcut)
    await flushPromises()
    await w.find('button').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="movement-token"]').text()).toContain('tok-123')
  })
})
