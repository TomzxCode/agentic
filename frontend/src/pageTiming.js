// Where the app spends its time: one visit per stretch a page is open and
// visible in front of the user, recorded from the router and posted to the API.
//
// A visit ends on navigation, when the tab goes to the background, and after
// IDLE_MS without input. The last rule keeps a tab left open (or a laptop that
// went to sleep) from reporting hours of time nobody spent, while still
// counting a long read as IDLE_MS of attention. The server drops anything under
// a second or over a day, and the client applies the same floor so a flash
// redirect never reaches it.

const ENDPOINT = '/api/page-visits'
const PROVENANCE_HEADERS = { 'X-Agentic-Client': 'web', 'X-Agentic-Actor': 'human' }

export const MIN_VISIT_MS = 1000
export const IDLE_MS = 15 * 60 * 1000
const IDLE_CHECK_MS = 30 * 1000
const INPUT_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll', 'focus']
const PALETTE_SIZE = 8

// Queue visits and post them in batches; a report that fails is dropped rather
// than interrupting the user, and keepalive lets the last one leave as the page
// unloads.
export function createVisitSender(fetchFn = (...args) => fetch(...args)) {
  let queue = []
  let sending = false
  let scheduled = false

  async function flush() {
    if (sending || !queue.length) return
    const batch = queue.slice(0, 100)
    queue = queue.slice(batch.length)
    sending = true
    try {
      await fetchFn(ENDPOINT, {
        method: 'POST',
        keepalive: true,
        headers: { 'Content-Type': 'application/json', ...PROVENANCE_HEADERS },
        body: JSON.stringify({ visits: batch })
      })
    } catch {
      // The visit is lost; tracking never blocks or nags the user.
    } finally {
      sending = false
      if (queue.length) schedule()
    }
  }

  // Sends that land together (a hide right after a navigation) go in one POST.
  function schedule() {
    if (scheduled || sending) return
    scheduled = true
    queueMicrotask(() => {
      scheduled = false
      void flush()
    })
  }

  return {
    send(visit) {
      queue.push(visit)
      schedule()
    }
  }
}

// Follow the router and the tab's visibility, and hand each finished visit to
// `send`. Returns a function that stops tracking (the tests use it; the app
// installs it once and keeps it for the session).
export function installPageTiming(
  router,
  {
    window: windowRef = window,
    document: documentRef = document,
    send = createVisitSender().send,
    now = () => Date.now(),
    idleMs = IDLE_MS
  } = {}
) {
  let current = null
  let lastInput = now()
  let idle = false

  function open(route) {
    if (!route || route.name == null) return
    // A page loaded in a background tab has not been looked at yet; the
    // visibility handler opens it when the tab comes forward.
    if (documentRef && documentRef.visibilityState === 'hidden') return
    const at = now()
    current = {
      path: route.fullPath || String(route.path || ''),
      route_name: String(route.name),
      title: (route.meta && route.meta.title) || String(route.name),
      startedAt: at
    }
    lastInput = at
    idle = false
    if (current.title && documentRef) documentRef.title = `${current.title} · Agentic`
  }

  function close(endAt = now()) {
    if (!current) return null
    const end = Math.max(current.startedAt, endAt)
    const visit = {
      path: current.path,
      route_name: current.route_name,
      title: current.title,
      started_at: new Date(current.startedAt).toISOString(),
      ended_at: new Date(end).toISOString(),
      duration_ms: end - current.startedAt
    }
    current = null
    return visit.duration_ms >= MIN_VISIT_MS ? visit : null
  }

  function flush(endAt) {
    const visit = close(endAt)
    if (visit) send(visit)
  }

  function onNavigate(to, from, failure) {
    if (failure) return
    if (current && current.path === to.fullPath && current.route_name === String(to.name)) return
    flush()
    open(to)
  }

  function onVisibility() {
    if (documentRef.visibilityState === 'hidden') {
      flush()
    } else if (!current) {
      open(router.currentRoute && router.currentRoute.value)
    }
  }

  function onPageHide() {
    flush()
  }

  function onPageShow(event) {
    if (event && event.persisted && !current) open(router.currentRoute && router.currentRoute.value)
  }

  // Any interaction marks the page as attended; after an idle close it starts a
  // new visit rather than stretching the old one.
  function onInput() {
    lastInput = now()
    if (!current && (!documentRef || documentRef.visibilityState !== 'hidden')) {
      open(router.currentRoute && router.currentRoute.value)
    }
  }

  const unregister = router.afterEach(onNavigate)
  windowRef.addEventListener('visibilitychange', onVisibility)
  windowRef.addEventListener('pagehide', onPageHide)
  windowRef.addEventListener('pageshow', onPageShow)
  for (const name of INPUT_EVENTS) windowRef.addEventListener(name, onInput, { passive: true })
  const idleTimer = windowRef.setInterval(() => {
    if (!current || idle || now() - lastInput < idleMs) return
    idle = true
    flush(lastInput + idleMs)
  }, IDLE_CHECK_MS)

  return function stop() {
    flush()
    if (typeof unregister === 'function') unregister()
    windowRef.removeEventListener('visibilitychange', onVisibility)
    windowRef.removeEventListener('pagehide', onPageHide)
    windowRef.removeEventListener('pageshow', onPageShow)
    for (const name of INPUT_EVENTS) windowRef.removeEventListener(name, onInput)
    windowRef.clearInterval(idleTimer)
  }
}

// The browser's offset from UTC in minutes, east positive, which is the sign
// the server's day bucketing expects.
export function tzOffsetMinutes(date = new Date()) {
  return -date.getTimezoneOffset()
}

export function localDayKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// A value for <input type="datetime-local">, which reads and writes local wall
// clock time with no zone.
export function toDateTimeLocal(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${localDayKey(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// The instant a <input type="datetime-local"> value names, or null when it is
// incomplete. The browser reads the bare value as local time.
export function fromDateTimeLocal(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS
const WEEK_MS = 7 * DAY_MS

export { DAY_MS }

// Tick spacing for a range: keep roughly four to eight labels, and switch to
// day-scale steps once the range is two days or longer, because hour labels
// repeat across days.
const HOUR_STEPS = [5 * MINUTE_MS, 15 * MINUTE_MS, 30 * MINUTE_MS, HOUR_MS, 2 * HOUR_MS, 3 * HOUR_MS, 6 * HOUR_MS]
const DAY_STEPS = [DAY_MS, 2 * DAY_MS, WEEK_MS, 2 * WEEK_MS, 30 * DAY_MS]

export function tickStep(spanMs) {
  const ladder = spanMs >= 2 * DAY_MS ? DAY_STEPS : HOUR_STEPS
  const step = ladder.find((candidate) => spanMs / candidate <= 8)
  return step || DAY_STEPS[DAY_STEPS.length - 1]
}

function tickLabel(date, step, spanMs) {
  const pad = (n) => String(n).padStart(2, '0')
  if (step < DAY_MS) {
    const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`
    return spanMs > DAY_MS ? `${date.toLocaleDateString(undefined, { weekday: 'short' })} ${time}` : time
  }
  if (step < WEEK_MS) return `${date.toLocaleDateString(undefined, { weekday: 'short' })} ${dayNumber(date)}`
  if (spanMs > 240 * DAY_MS) return date.toLocaleDateString(undefined, { month: 'short' })
  return `${date.toLocaleDateString(undefined, { month: 'short' })} ${dayNumber(date)}`
}

function dayNumber(date) {
  return date.toLocaleDateString(undefined, { day: 'numeric' })
}

// Local-time ticks across a range: anchored at the local midnight of the start
// day, then stepped forward. Day-scale steps move by the calendar rather than
// by 24 hours, so a DST change does not drift every later tick by an hour.
export function timelineTicks(startMs, endMs) {
  const span = endMs - startMs
  if (!Number.isFinite(span) || span <= 0) return []
  const step = tickStep(span)
  const cursor = new Date(startMs)
  cursor.setHours(0, 0, 0, 0)
  const ticks = []
  for (let guard = 0; guard < 64; guard += 1) {
    const at = cursor.getTime()
    if (at > endMs) break
    if (at >= startMs) {
      ticks.push({
        at,
        left: ((at - startMs) / span) * 100,
        label: tickLabel(cursor, step, span)
      })
    }
    if (step >= DAY_MS) {
      cursor.setDate(cursor.getDate() + Math.round(step / DAY_MS))
    } else {
      cursor.setTime(at + step)
    }
  }
  return ticks
}

// Where a visit sits in a range, as percentages, clipped to its bounds. A visit
// shorter than the minimum is still drawn as a sliver.
export function blockInRange(startIso, endIso, rangeStartMs, rangeEndMs) {
  const span = rangeEndMs - rangeStartMs
  const start = new Date(startIso).getTime()
  const end = new Date(endIso).getTime()
  if (!Number.isFinite(span) || span <= 0 || Number.isNaN(start) || Number.isNaN(end)) {
    return { left: 0, width: 0.4 }
  }
  const left = ((Math.max(start, rangeStartMs) - rangeStartMs) / span) * 100
  const right = ((Math.min(end, rangeEndMs) - rangeStartMs) / span) * 100
  return { left: Math.max(0, Math.min(100, left)), width: Math.max(0.4, Math.max(0, Math.min(100, right) - left)) }
}

// The instant a local day (YYYY-MM-DD) starts.
export function dayStartMs(key) {
  const [year, month, day] = String(key).split('-').map(Number)
  if (!year || !month || !day) return NaN
  return new Date(year, month - 1, day).getTime()
}

export function formatVisitDuration(ms) {
  const total = Math.max(0, Number(ms) || 0)
  if (total < 60_000) return `${Math.max(1, Math.round(total / 1000))}s`
  const minutes = Math.round(total / 60_000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${String(rest).padStart(2, '0')}m` : `${hours}h`
}

export function formatClockTime(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

// A visit's moment with its date in front, for a range that spans more than one
// day and would otherwise show repeated clock times.
export function formatDateTimeShort(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${formatClockTime(iso)}`
}

// The part of a visit that falls inside a range, in milliseconds.
export function overlapMs(startIso, endIso, rangeStartMs, rangeEndMs) {
  const start = new Date(startIso).getTime()
  const end = new Date(endIso).getTime()
  if (Number.isNaN(start) || Number.isNaN(end)) return 0
  return Math.max(0, Math.min(end, rangeEndMs) - Math.max(start, rangeStartMs))
}

export function formatDayLabel(key) {
  const start = dayStartMs(key)
  if (Number.isNaN(start)) return key
  return new Date(start).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  })
}

// A stable colour per page key, so a page keeps its colour across the timeline,
// the bars, and the trend.
export function pageColor(key) {
  const text = String(key || '')
  let hash = 0
  for (let index = 0; index < text.length; index += 1) hash = (hash * 31 + text.charCodeAt(index)) >>> 0
  return `time-color-${(hash % PALETTE_SIZE) + 1}`
}
