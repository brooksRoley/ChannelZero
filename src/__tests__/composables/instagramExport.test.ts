import { describe, it, expect, beforeEach } from 'vitest'
import {
  clearActivity, kindOf, loadActivity, parseExport, recordsOf, saveActivity, timestampOf, totals,
} from '@/composables/instagramExport'

const NOW = new Date(2026, 9, 30, 20, 0) // Oct 30 2026, local
const at = (y: number, m: number, d: number, h: number) => Math.floor(new Date(y, m - 1, d, h).getTime() / 1000)

// Shapes seen in real exports; field names differ between versions.
const LIKES = JSON.stringify({
  likes_media_likes: [
    { title: 'someone', string_list_data: [{ href: 'https://instagram.com/p/x', value: '👍', timestamp: at(2026, 10, 30, 9) }] },
    { title: 'other', string_list_data: [{ href: 'https://instagram.com/p/y', value: '👍', timestamp: at(2026, 10, 30, 22) }] },
  ],
})
const COMMENTS = JSON.stringify([
  { string_map_data: { Comment: { value: 'nice' }, 'Media Owner': { value: 'someone' }, Time: { timestamp: at(2026, 10, 29, 9) } } },
])
const SAVED = JSON.stringify({
  saved_saved_media: [{ title: 'someone', string_map_data: { 'Saved on': { href: 'https://x', timestamp: at(2026, 10, 28, 9) } } }],
})
const POSTS = JSON.stringify([{ media: [{ uri: 'media/posts/1.jpg', creation_timestamp: at(2026, 10, 1, 18), title: 'caption' }] }])

const files = [
  { path: 'export/your_instagram_activity/likes/liked_posts.json', text: LIKES },
  { path: 'export/your_instagram_activity/comments/post_comments_1.json', text: COMMENTS },
  { path: 'export/your_instagram_activity/saved/saved_posts.json', text: SAVED },
  { path: 'export/your_instagram_activity/content/posts_1.json', text: POSTS },
  { path: 'export/personal_information/personal_information.json', text: '{"profile_user": []}' },
]

describe('instagramExport', () => {
  beforeEach(() => localStorage.clear())

  it('files each export file under its kind, likes before comments', () => {
    expect(kindOf('a/likes/liked_comments.json')).toBe('like')
    expect(kindOf('a/comments/reels_comments.json')).toBe('comment')
    expect(kindOf('a\\content\\posts_2.json')).toBe('post')
    expect(kindOf('a/personal_information/personal_information.json')).toBeNull()
  })

  it('finds records by shape and times by any *timestamp field, seconds or ms', () => {
    expect(recordsOf({ meta: 'x', items: [{ a: 1 }] })).toEqual([{ a: 1 }])
    expect(timestampOf({ deep: { list: [{ timestamp: 1_700_000_000_000 }] } })).toBe(1_700_000_000)
    expect(timestampOf({ value: 'no time here', count: 42 })).toBeNull()
  })

  it('counts activity per local day and hour, newest first', () => {
    const a = parseExport(files, NOW)
    expect(a.days.map((d) => d.date)).toEqual(['2026-10-30', '2026-10-29', '2026-10-28', '2026-10-01'])
    expect(a.days[0]).toMatchObject({ like: 2, comment: 0 })
    expect(a.hours[9]).toBe(3)
    expect(a.skipped).toBe(1)
    expect(totals(a, 7, NOW)).toEqual({ like: 2, comment: 1, save: 1, post: 0, story: 0 })
  })

  it('keeps no usernames, links, captions or comment text', () => {
    const stored = JSON.stringify(parseExport(files, NOW))
    for (const s of ['someone', 'instagram.com', 'nice', 'caption', 'media/posts']) expect(stored).not.toContain(s)
  })

  it('reports a file it could not date, and an HTML export', () => {
    const a = parseExport([{ path: 'x/likes/liked_posts.json', text: '{"likes":[{"title":"a"}]}' }], NOW)
    expect(a.files[0]).toMatchObject({ records: 1, dated: 0 })
    expect(parseExport([{ path: 'x/likes/liked_posts.html', text: '<html>' }], NOW).htmlOnly).toBe(true)
  })

  it('drops activity older than the keep window', () => {
    const old = JSON.stringify([{ media: [{ creation_timestamp: at(2024, 1, 1, 9) }] }])
    expect(parseExport([{ path: 'x/content/posts_1.json', text: old }], NOW).days).toEqual([])
  })

  it('stores only on this device and can be cleared', () => {
    const a = parseExport(files, NOW)
    saveActivity(a)
    expect(loadActivity()?.days.length).toBe(4)
    clearActivity()
    expect(loadActivity()).toBeNull()
  })
})
