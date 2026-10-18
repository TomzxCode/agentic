import { describe, expect, it } from 'vitest'
import { nextRuns, scheduleError } from '../cron'

describe('scheduleError', () => {
  it('accepts a valid five-field expression', () => {
    expect(scheduleError('0 9 * * *')).toBe('')
    expect(scheduleError('*/15 * * * *')).toBe('')
    expect(scheduleError('0 18 * * 5')).toBe('')
  })

  it('requires a value', () => {
    expect(scheduleError('')).toMatch(/required/)
    expect(scheduleError('   ')).toMatch(/required/)
  })

  it('requires exactly five fields, like the server', () => {
    expect(scheduleError('* * * *')).toMatch(/5 fields/)
    expect(scheduleError('0 9 * * * *')).toMatch(/5 fields/)
  })

  it('rejects an out-of-range field', () => {
    expect(scheduleError('60 9 * * *')).toMatch(/not a valid cron expression/)
    expect(scheduleError('0 25 * * *')).toMatch(/not a valid cron expression/)
  })
})

describe('nextRuns', () => {
  const from = new Date('2026-01-01T00:00:00Z')

  it('lists the next runs in order, read in the given zone', () => {
    const runs = nextRuns('0 9 * * *', 'UTC', 5, from)
    expect(runs).toHaveLength(5)
    expect(runs[0]).toBe('2026-01-01T09:00:00.000Z')
    expect(runs[4]).toBe('2026-01-05T09:00:00.000Z')
  })

  it('reads the wall clock in the task zone', () => {
    // 09:00 in Tokyo is 00:00 UTC.
    const runs = nextRuns('0 9 * * *', 'Asia/Tokyo', 2, new Date('2025-12-31T23:00:00Z'))
    expect(runs[0]).toBe('2026-01-01T00:00:00.000Z')
    expect(runs[1]).toBe('2026-01-02T00:00:00.000Z')
  })

  it('steps a sub-hour expression', () => {
    const runs = nextRuns('*/15 * * * *', 'UTC', 3, from)
    expect(runs).toEqual(['2026-01-01T00:15:00.000Z', '2026-01-01T00:30:00.000Z', '2026-01-01T00:45:00.000Z'])
  })
})
