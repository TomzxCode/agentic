import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  deadlineInfo,
  formatDeadline,
  formatDuration,
  prStatus,
  statusClass,
  statusDurations,
  statusLabel,
  store,
  timeAgo
} from '../store'

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

describe('prStatus', () => {
  const pr = (over = {}) => ({ kind: 'pull_request', metadata_json: { state: 'OPEN' }, ...over })

  it('is null for non-PR items or ones without a fetched state', () => {
    expect(prStatus(null)).toBeNull()
    expect(prStatus({ kind: 'issue', metadata_json: { state: 'OPEN' } })).toBeNull()
    expect(prStatus({ kind: 'pull_request', metadata_json: {} })).toBeNull()
  })

  it('maps each PR state to a label and badge class', () => {
    expect(prStatus(pr())).toEqual({ label: 'Open', className: 'pr-open' })
    expect(prStatus(pr({ metadata_json: { state: 'MERGED' } }))).toEqual({ label: 'Merged', className: 'pr-merged' })
    expect(prStatus(pr({ metadata_json: { state: 'CLOSED' } }))).toEqual({ label: 'Closed', className: 'pr-closed' })
  })

  it('shows an open PR flagged as a draft as Draft', () => {
    expect(prStatus(pr({ metadata_json: { state: 'OPEN', is_draft: true } }))).toEqual({
      label: 'Draft',
      className: 'pr-draft'
    })
  })

  it('accepts the kind recorded in the fetched metadata', () => {
    expect(prStatus({ kind: '', metadata_json: { kind: 'pull_request', state: 'MERGED' } })).toEqual({
      label: 'Merged',
      className: 'pr-merged'
    })
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

describe('formatDuration', () => {
  it('rounds each bucket to a readable value', () => {
    expect(formatDuration(0)).toBe('<1m')
    expect(formatDuration(30_000)).toBe('<1m')
    expect(formatDuration(5 * 60_000)).toBe('5m')
    expect(formatDuration(3 * 3_600_000 + 20 * 60_000)).toBe('3h 20m')
    expect(formatDuration(2 * 86_400_000 + 4 * 3_600_000)).toBe('2d 4h')
  })

  it('never goes below zero', () => {
    expect(formatDuration(-5000)).toBe('<1m')
  })
})

describe('statusDurations', () => {
  const task = (over = {}) => ({ status: 'open', created_at: '2026-01-01T00:00:00Z', ...over })

  it('is empty without a task or creation time', () => {
    expect(statusDurations(null, [])).toEqual([])
    expect(statusDurations({ status: 'open' }, [])).toEqual([])
  })

  it('charges the whole span to the current status when it never changed', () => {
    const now = new Date('2026-01-01T02:00:00Z').getTime()
    expect(statusDurations(task(), [], now)).toEqual([{ status: 'open', ms: 2 * 3_600_000 }])
  })

  it('splits time across status changes and charges the rest to now', () => {
    const now = new Date('2026-01-01T03:00:00Z').getTime()
    const events = [
      {
        created_at: '2026-01-01T01:00:00Z',
        data_json: { changes: { status: { from: 'open', to: 'in_progress' } } }
      },
      {
        created_at: '2026-01-01T02:00:00Z',
        data_json: { changes: { status: { from: 'in_progress', to: 'done' } } }
      },
      // A non-status edit is ignored.
      { created_at: '2026-01-01T02:30:00Z', data_json: { changes: { title: { from: 'a', to: 'b' } } } }
    ]
    expect(statusDurations(task(), events, now)).toEqual([
      { status: 'open', ms: 3_600_000 },
      { status: 'in_progress', ms: 3_600_000 },
      { status: 'done', ms: 3_600_000 }
    ])
  })

  it('accumulates time when a status is re-entered', () => {
    const now = new Date('2026-01-01T03:00:00Z').getTime()
    const events = [
      { created_at: '2026-01-01T01:00:00Z', data_json: { changes: { status: { from: 'open', to: 'blocked' } } } },
      { created_at: '2026-01-01T02:00:00Z', data_json: { changes: { status: { from: 'blocked', to: 'open' } } } }
    ]
    expect(statusDurations(task(), events, now)).toEqual([
      { status: 'open', ms: 2 * 3_600_000 },
      { status: 'blocked', ms: 3_600_000 }
    ])
  })
})

describe('deadlineInfo', () => {
  const now = new Date('2026-06-15T12:00:00Z').getTime()
  const day = 86_400_000

  it('is null without a (parseable) deadline', () => {
    expect(deadlineInfo(null, now)).toBeNull()
    expect(deadlineInfo('not-a-date', now)).toBeNull()
  })

  it('flags an overdue deadline in the danger tone', () => {
    const info = deadlineInfo(new Date(now - 2 * day).toISOString(), now)
    expect(info.overdue).toBe(true)
    expect(info.tone).toBe('danger')
    expect(info.label).toContain('Overdue')
  })

  it('marks a deadline later today and tomorrow as due soon', () => {
    const endOfToday = new Date(now)
    endOfToday.setHours(23, 59, 0, 0)
    expect(deadlineInfo(endOfToday.toISOString(), now)).toEqual({
      overdue: false,
      tone: 'warn',
      label: 'Due today'
    })

    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    expect(deadlineInfo(tomorrow.toISOString(), now).label).toBe('Due tomorrow')
  })

  it('counts whole days for a later deadline', () => {
    const later = new Date(now + 3 * day)
    later.setHours(12, 0, 0, 0)
    expect(deadlineInfo(later.toISOString(), now)).toEqual({ overdue: false, tone: '', label: 'Due in 3d' })
  })
})

describe('formatDeadline', () => {
  it('is empty without a deadline', () => {
    expect(formatDeadline(null)).toBe('')
  })

  it('renders a parseable deadline in local time', () => {
    expect(formatDeadline('2026-06-15T12:00:00Z')).not.toBe('')
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
