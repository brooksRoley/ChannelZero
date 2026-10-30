import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InstagramImport from '@/components/InstagramImport.vue'

function pick(input: HTMLInputElement, files: { path: string; text: string }[]) {
  const list = files.map(({ path, text }) => {
    const f = new File([text], path.split('/').pop()!, { type: 'application/json' })
    Object.defineProperty(f, 'webkitRelativePath', { value: path })
    return f
  })
  Object.defineProperty(input, 'files', { value: list, configurable: true })
  input.dispatchEvent(new Event('change'))
}

const ts = Math.floor(Date.now() / 1000) - 3600
const likes = JSON.stringify({ likes_media_likes: [{ title: 'someone', string_list_data: [{ timestamp: ts }] }] })

describe('InstagramImport', () => {
  beforeEach(() => localStorage.clear())

  it('says the API is retired and offers the export', () => {
    const w = mount(InstagramImport)
    expect(w.text()).toContain('Business and Creator')
    expect(w.text()).toContain('Choose the export folder')
    expect(w.find('[data-testid="instagram-summary"]').exists()).toBe(false)
  })

  it('reads a picked export folder into counts, kept on the device', async () => {
    const w = mount(InstagramImport)
    pick(w.find('[data-testid="instagram-folder"]').element as HTMLInputElement,
      [{ path: 'ig/your_instagram_activity/likes/liked_posts.json', text: likes }])
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
    await flushPromises()
    expect(w.find('[data-testid="instagram-summary"]').text()).toContain('1 like')
    expect(localStorage.getItem('cz-instagram-activity')).not.toContain('someone')
  })

  it('names an HTML export instead of showing nothing', async () => {
    const w = mount(InstagramImport)
    pick(w.find('[data-testid="instagram-folder"]').element as HTMLInputElement,
      [{ path: 'ig/likes/liked_posts.html', text: '<html>' }])
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
    await flushPromises()
    expect(w.find('[data-testid="instagram-note"]').text()).toContain('JSON')
  })
})
