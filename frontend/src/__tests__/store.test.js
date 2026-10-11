import { afterEach, describe, expect, it, vi } from 'vitest'
import { statusClass, statusLabel, store, timeAgo } from '../store'

describe('statusLabel', () => {
  it('maps every known status to a human label', () => {
    expect(statusLabel('open')).toBe('Open')
    expect(statusLabel('in_progress')).toBe('In progress')
    expect(statusLabel('blocked')).toBe('Blocked')
    expect(statusLabel('done')).toBe('Done')
    expect(statusLabel('archived')).toBe('Archived')
  })

  it('falls through to the raw value for unknown statuses', () => {
    expect(statusLabel('weird')).toBe('weird')
  })
})

describe('statusClass', () => {
  it('returns the badge styling for each status', () => {
    expect(statusClass('open')).toBe('badge')
    expect(statusClass('in_progress')).toBe('badge run')
    expect(statusClass('blocked')).toBe('badge warn')
    expect(statusClass('done')).toBe('badge ok')
    expect(statusClass('archived')).toBe('badge')
  })

  it('defaults unknown statuses to the plain badge', () => {
    expect(statusClass('weird')).toBe('badge')
  })
})

describe('timeAgo', () => {
  afterEach(() => vi.useRealTimers())

  it('is empty for a missing timestamp', () => {
    expect(timeAgo(null)).toBe('')
    expect(timeAgo(undefined)).toBe('')
  })

  it('formats each relative bucket', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-10T12:00:00Z'))
    const secondsAgo = (s) => new Date(Date.now() - s * 1000).toISOString()

    expect(timeAgo(secondsAgo(5))).toBe('just now')
    expect(timeAgo(secondsAgo(5 * 60))).toBe('5m ago')
    expect(timeAgo(secondsAgo(3 * 3600))).toBe('3h ago')
    expect(timeAgo(secondsAgo(2 * 86400))).toBe('2d ago')
  })

  it('clamps future timestamps to just now', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-10T12:00:00Z'))
    expect(timeAgo(new Date(Date.now() + 60_000).toISOString())).toBe('just now')
  })
})

describe('store.notify', () => {
  afterEach(() => vi.useRealTimers())

  it('shows a toast and clears it after a delay', () => {
    vi.useFakeTimers()
    store.notify('saved')
    expect(store.toast).toEqual({ message: 'saved', isError: false })

    store.notify('boom', true)
    expect(store.toast).toEqual({ message: 'boom', isError: true })

    vi.advanceTimersByTime(4000)
    expect(store.toast).toBeNull()
  })
})
