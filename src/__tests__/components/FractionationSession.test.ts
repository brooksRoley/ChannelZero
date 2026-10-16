import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'

const eye = {
  status: ref('off'),
  eyesClosed: ref(false),
  start: vi.fn(async () => {}),
  stop: vi.fn(),
  onChange: vi.fn(() => () => {}),
}
const voice = {
  say: vi.fn(() => new Promise<void>(() => {})),
  cancel: vi.fn(),
  backend: ref('speech'),
  kokoroStatus: ref('off'),
  enableKokoro: vi.fn(async () => true),
  disableKokoro: vi.fn(),
}
const running = ref(false)
const session = {
  start: vi.fn(async () => { running.value = true }),
  stop: vi.fn(() => { running.value = false }),
  stage: ref('induce'),
  round: ref(1),
  rounds: computed(() => 3),
  running,
  camera: ref(false),
}

vi.mock('tone', () => ({ start: vi.fn(async () => {}) }))
vi.mock('@/composables/useEyeState', () => ({ useEyeState: () => eye }))
vi.mock('@/composables/useVoice', () => ({ useVoice: () => voice }))
vi.mock('@/composables/useTranceEngine', () => ({
  useTranceEngine: () => ({ completedSession: ref(null) }),
}))
vi.mock('@/composables/useFractionation', () => ({ useFractionationSession: () => session }))

import FractionationSession from '@/components/FractionationSession.vue'

describe('FractionationSession', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    running.value = false
    eye.status.value = 'off'
  })

  it('shows the consent card with the camera off by default and the privacy note', () => {
    const w = mount(FractionationSession)
    expect(w.text()).toContain('Fractionation')
    expect(w.text()).toContain('Headphones are recommended')
    const cam = w.find('[data-test="camera-toggle"]')
    expect(cam.attributes('aria-checked')).toBe('false')
    expect(w.find('[data-test="privacy-note"]').text()).toContain(
      'Runs entirely on this device. No video leaves your browser or is stored.',
    )
    expect(w.text()).toContain('It isn’t a measure of trance.')
    expect(w.find('[data-test="voice-toggle"]').attributes('aria-checked')).toBe('false')
  })

  it('Begin without the camera starts a timed session and never touches the camera', async () => {
    const w = mount(FractionationSession)
    await w.find('[data-test="begin"]').trigger('click')
    await flushPromises()

    expect(eye.start).not.toHaveBeenCalled()
    expect(voice.enableKokoro).not.toHaveBeenCalled()
    expect(session.start).toHaveBeenCalledWith({ camera: false })
    expect(w.find('[data-test="begin"]').exists()).toBe(false)
    expect(w.text()).toContain('round 1 of 3')
    expect(w.text()).toContain('timed')
  })

  it('falls back to timing with a soft note when the camera is denied', async () => {
    eye.start.mockImplementationOnce(async () => { eye.status.value = 'denied' })
    const w = mount(FractionationSession)
    await w.find('[data-test="camera-toggle"]').trigger('click')
    await w.find('[data-test="begin"]').trigger('click')
    await flushPromises()

    expect(eye.start).toHaveBeenCalledTimes(1)
    expect(session.start).toHaveBeenCalledWith({ camera: false })
    // The card is gone once running; End stops the session.
    await w.find('[data-test="end"]').trigger('click')
    expect(session.stop).toHaveBeenCalled()
    expect(w.text()).toContain('gentle timing instead')
  })
})
