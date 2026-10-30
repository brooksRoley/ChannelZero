import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StravaCallback from '@/views/StravaCallback.vue'

// ── Top-level mutable mock state ──────────────────────────────────

const mockQuery: Record<string, string> = {}
const mockReplace = vi.fn()
const mockMarkConnected = vi.fn()

vi.mock('vue-router', () => ({
  useRoute:  () => ({ query: mockQuery }),
  useRouter: () => ({ replace: mockReplace }),
}))

vi.mock('@/composables/useVibeStore', () => ({
  useVibeStore: () => ({ markConnected: mockMarkConnected }),
}))

function setQuery(q: Record<string, string>) {
  Object.keys(mockQuery).forEach(k => delete mockQuery[k])
  Object.assign(mockQuery, q)
}

function stubFetch(ok: boolean, status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok, status,
    json: () => Promise.resolve(body),
  }))
}

async function mountCallback() {
  const wrapper = mount(StravaCallback)
  await flushPromises()
  return wrapper
}

// ── Tests ──────────────────────────────────────────────────────────

describe('StravaCallback', () => {
  beforeEach(() => {
    mockReplace.mockReset()
    mockMarkConnected.mockReset()
    setQuery({})
    stubFetch(true, 200, {})
  })

  it('calls /api/strava/callback with code and state as query string params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
    setQuery({ code: 'strava-code', state: 'csrf-state' })

    await mountCallback()

    const [url] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/strava/callback')
    expect(url).toContain('code=strava-code')
    expect(url).toContain('state=csrf-state')
  })

  it('URL-encodes code and state values in the request URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
    setQuery({ code: 'co de+special', state: 'st&ate=1' })

    await mountCallback()

    const [url] = fetchMock.mock.calls[0]
    // raw spaces and special chars must not appear unencoded
    expect(url).not.toContain('co de')
    expect(url).toContain(encodeURIComponent('co de+special'))
  })

  it('calls markConnected("strava") on a successful backend response', async () => {
    setQuery({ code: 'code', state: 'state' })
    await mountCallback()

    expect(mockMarkConnected).toHaveBeenCalledOnce()
    expect(mockMarkConnected).toHaveBeenCalledWith('strava')
  })

  it('redirects to /peripheral on success', async () => {
    setQuery({ code: 'code', state: 'state' })
    await mountCallback()

    expect(mockReplace).toHaveBeenCalledWith('/peripheral')
  })

  it('shows error and skips markConnected when code param is absent', async () => {
    setQuery({ state: 'state-only' })
    const wrapper = await mountCallback()

    expect(mockMarkConnected).not.toHaveBeenCalled()
    expect(mockReplace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Missing authorization code or state')
  })

  it('shows error and skips markConnected when state param is absent', async () => {
    setQuery({ code: 'code-only' })
    const wrapper = await mountCallback()

    expect(mockMarkConnected).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Missing authorization code or state')
  })

  it('shows the backend detail message when the callback request fails', async () => {
    stubFetch(false, 400, { detail: 'Invalid Strava code' })
    setQuery({ code: 'c', state: 's' })
    const wrapper = await mountCallback()

    expect(mockMarkConnected).not.toHaveBeenCalled()
    expect(mockReplace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Invalid Strava code')
  })

  it('shows a fallback error when the backend returns no detail field', async () => {
    stubFetch(false, 500, {})
    setQuery({ code: 'c', state: 's' })
    const wrapper = await mountCallback()

    expect(wrapper.text()).toContain('Strava callback failed')
  })

  it('shows a network error message when fetch itself rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    setQuery({ code: 'c', state: 's' })
    const wrapper = await mountCallback()

    expect(mockMarkConnected).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Network error')
  })

  it('shows a plain message and never calls the backend when Strava says access was denied', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    setQuery({ error: 'access_denied', state: 's' })
    const wrapper = await mountCallback()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('access was declined')
    expect(mockMarkConnected).not.toHaveBeenCalled()
  })

  it('passes the granted scope through to the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
    setQuery({ code: 'c', state: 's', scope: 'read,activity:read' })
    await mountCallback()
    expect(fetchMock.mock.calls[0][0]).toContain(`scope=${encodeURIComponent('read,activity:read')}`)
  })

  it('shows the message from a {code, message} detail (an inactive Strava app)', async () => {
    stubFetch(false, 503, { detail: { code: 'app_inactive', message: "Strava isn't sending activities right now" } })
    setQuery({ code: 'c', state: 's' })
    const wrapper = await mountCallback()
    expect(wrapper.text()).toContain("Strava isn't sending activities right now")
    expect(mockMarkConnected).not.toHaveBeenCalled()
  })
})
