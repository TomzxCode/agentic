import { describe, expect, it, vi } from 'vitest'
import {
  DAY_MS,
  blockInRange,
  createVisitSender,
  dayStartMs,
  formatVisitDuration,
  fromDateTimeLocal,
  installPageTiming,
  localDayKey,
  overlapMs,
  pageColor,
  tickStep,
  timelineTicks,
  toDateTimeLocal,
  tzOffsetMinutes
} from '../pageTiming'

function fakeRouter() {
  const callbacks = []
  const router = {
    currentRoute: { value: null },
    afterEach(fn) {
      callbacks.push(fn)
      return () => {}
    },
    navigate(route) {
      const from = router.currentRoute.value
      router.currentRoute.value = route
      for (const fn of callbacks) fn(route, from)
    }
  }
  return router
}

function fakeWindow() {
  const listeners = new Map()
  let interval = null
  return {
    addEventListener(name, fn) {
      if (!listeners.has(name)) listeners.set(name, [])
      listeners.get(name).push(fn)
    },
    removeEventListener(name, fn) {
      listeners.set(
        name,
        (listeners.get(name) || []).filter((entry) => entry !== fn)
      )
    },
    setInterval(fn) {
      interval = fn
      return 1
    },
    clearInterval() {
      interval = null
    },
    dispatch(name, event = {}) {
      for (const fn of listeners.get(name) || []) fn(event)
    },
    tick() {
      if (interval) interval()
    }
  }
}

const tasksRoute = { fullPath: '/', name: 'tasks', meta: { title: 'Tasks' } }
const inboxRoute = { fullPath: '/inbox', name: 'inbox', meta: { title: 'Inbox' } }

describe('pageTiming helpers', () => {
  it('formats a visit length at the scale it reads best', () => {
    expect(formatVisitDuration(0)).toBe('1s')
    expect(formatVisitDuration(30_000)).toBe('30s')
    expect(formatVisitDuration(5 * 60_000)).toBe('5m')
    expect(formatVisitDuration(65 * 60_000)).toBe('1h 05m')
    expect(formatVisitDuration(120 * 60_000)).toBe('2h')
  })

  it('keys a day and its start in local time', () => {
    const key = localDayKey(new Date(2026, 0, 5, 23, 30))
    expect(key).toBe('2026-01-05')
    expect(dayStartMs(key)).toBe(new Date(2026, 0, 5, 0, 0).getTime())
    expect(tzOffsetMinutes()).toBe(-new Date().getTimezoneOffset())
  })

  it('gives a page the same colour every time', () => {
    expect(pageColor('tasks')).toBe(pageColor('tasks'))
    expect(pageColor('tasks')).toMatch(/^time-color-[1-8]$/)
  })

  it('reads and writes the datetime-local format in local time', () => {
    expect(toDateTimeLocal(new Date(2026, 0, 5, 9, 7))).toBe('2026-01-05T09:07')
    expect(fromDateTimeLocal('2026-01-05T09:07').getTime()).toBe(new Date(2026, 0, 5, 9, 7).getTime())
    expect(fromDateTimeLocal('')).toBeNull()
    expect(fromDateTimeLocal('not a date')).toBeNull()
  })

  it('ticks a short range by the clock and a long one by the day', () => {
    const start = new Date(2026, 9, 28, 10, 0).getTime()
    const hourTicks = timelineTicks(start, start + 60 * 60_000)
    expect(hourTicks.map((tick) => tick.label)).toEqual(['10:00', '10:15', '10:30', '10:45', '11:00'])
    expect(hourTicks[0].left).toBe(0)
    expect(hourTicks.at(-1).left).toBe(100)

    const dayStart = new Date(2026, 9, 28, 0, 0).getTime()
    const weekTicks = timelineTicks(dayStart, dayStart + 7 * DAY_MS)
    expect(tickStep(7 * DAY_MS)).toBe(DAY_MS)
    expect(weekTicks.length).toBeGreaterThan(1)
    expect(weekTicks.length).toBeLessThanOrEqual(8)
    expect(weekTicks[0].left).toBe(0)
    expect(weekTicks.every((tick) => tick.left >= 0 && tick.left <= 100)).toBe(true)
  })

  it('places a visit in its range and clips one that crosses an edge', () => {
    const start = new Date(2026, 9, 28, 10, 0).getTime()
    const end = start + 60 * 60_000

    const inside = blockInRange(
      new Date(start + 15 * 60_000).toISOString(),
      new Date(start + 45 * 60_000).toISOString(),
      start,
      end
    )
    expect(inside.left).toBeCloseTo(25, 5)
    expect(inside.width).toBeCloseTo(50, 5)

    const clipped = blockInRange(
      new Date(start - 60_000).toISOString(),
      new Date(start + 60_000).toISOString(),
      start,
      end
    )
    expect(clipped.left).toBe(0)
    expect(clipped.width).toBeCloseTo(100 / 60, 5)

    const after = blockInRange(new Date(end + 60_000).toISOString(), new Date(end + 120_000).toISOString(), start, end)
    expect(after.width).toBe(0.4)
  })

  it('counts only the part of a visit inside the range', () => {
    const start = new Date(2026, 9, 28, 10, 0).getTime()
    const end = start + 60 * 60_000

    expect(
      overlapMs(new Date(start + 15 * 60_000).toISOString(), new Date(start + 45 * 60_000).toISOString(), start, end)
    ).toBe(30 * 60_000)
    expect(overlapMs(new Date(start - 60_000).toISOString(), new Date(start + 60_000).toISOString(), start, end)).toBe(
      60_000
    )
    expect(overlapMs(new Date(end + 60_000).toISOString(), new Date(end + 120_000).toISOString(), start, end)).toBe(0)
  })
})

describe('createVisitSender', () => {
  it('posts buffered visits in one batch with provenance and keepalive', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true })
    const sender = createVisitSender(fetchFn)

    sender.send({ path: '/', duration_ms: 1000 })
    sender.send({ path: '/inbox', duration_ms: 2000 })
    await Promise.resolve()
    await Promise.resolve()

    expect(fetchFn).toHaveBeenCalledTimes(1)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe('/api/page-visits')
    expect(init.method).toBe('POST')
    expect(init.keepalive).toBe(true)
    expect(init.headers['X-Agentic-Client']).toBe('web')
    expect(JSON.parse(init.body).visits).toHaveLength(2)
  })

  it('never throws when the report fails', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('offline'))
    const sender = createVisitSender(fetchFn)
    expect(() => sender.send({ path: '/', duration_ms: 1000 })).not.toThrow()
    await Promise.resolve()
  })
})

describe('installPageTiming', () => {
  it('records a visit per navigation and sends it when the page changes', () => {
    const router = fakeRouter()
    const windowRef = fakeWindow()
    const documentRef = { visibilityState: 'visible', title: '' }
    let clock = 1_000_000
    const send = vi.fn()

    installPageTiming(router, { window: windowRef, document: documentRef, send, now: () => clock })
    router.navigate(tasksRoute)
    expect(documentRef.title).toBe('Tasks · Agentic')

    clock += 30_000
    router.navigate(inboxRoute)

    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0]).toMatchObject({
      path: '/',
      route_name: 'tasks',
      title: 'Tasks',
      duration_ms: 30_000
    })
  })

  it('ends the visit when the tab hides and starts a new one when it returns', () => {
    const router = fakeRouter()
    const windowRef = fakeWindow()
    const documentRef = { visibilityState: 'visible', title: '' }
    let clock = 1_000_000
    const send = vi.fn()

    installPageTiming(router, { window: windowRef, document: documentRef, send, now: () => clock })
    router.navigate(tasksRoute)
    clock += 12_000

    documentRef.visibilityState = 'hidden'
    windowRef.dispatch('visibilitychange')
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0].duration_ms).toBe(12_000)

    clock += 3_600_000 // an hour in the background is not time in the app
    documentRef.visibilityState = 'visible'
    windowRef.dispatch('visibilitychange')
    clock += 8_000
    windowRef.dispatch('pagehide')

    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.calls[1][0].duration_ms).toBe(8_000)
  })

  it('closes an idle visit at the idle limit, then reopens on the next input', () => {
    const router = fakeRouter()
    const windowRef = fakeWindow()
    const documentRef = { visibilityState: 'visible', title: '' }
    let clock = 1_000_000
    const send = vi.fn()

    installPageTiming(router, {
      window: windowRef,
      document: documentRef,
      send,
      now: () => clock,
      idleMs: 15 * 60_000
    })
    router.navigate(tasksRoute)

    clock += 20 * 60_000 // no input for 20 minutes
    windowRef.tick()

    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0].duration_ms).toBe(15 * 60_000)

    clock += 5_000
    windowRef.dispatch('pointerdown')
    clock += 4_000
    windowRef.dispatch('pagehide')

    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.calls[1][0].duration_ms).toBe(4_000)
  })

  it('drops a visit too short to be time spent', () => {
    const router = fakeRouter()
    const windowRef = fakeWindow()
    const documentRef = { visibilityState: 'visible', title: '' }
    let clock = 1_000_000
    const send = vi.fn()

    installPageTiming(router, { window: windowRef, document: documentRef, send, now: () => clock })
    router.navigate(tasksRoute)
    clock += 200
    router.navigate(inboxRoute)

    expect(send).not.toHaveBeenCalled()
  })
})
