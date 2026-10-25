import { recordApiCall } from './debug.js'

const API = '/api'

// Every request declares its provenance: the web UI is always a human.
const PROVENANCE_HEADERS = { 'X-Agentic-Client': 'web', 'X-Agentic-Actor': 'human' }

const pendingRequests = new Map()

async function executeRequest(path, method, body, bodyString) {
  const headers = { ...PROVENANCE_HEADERS }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const start =
    typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now()
  const res = await fetch(API + path, {
    method,
    headers,
    body: bodyString
  })
  const duration =
    (typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now()) -
    start
  const getHeader = (name) => (res.headers && typeof res.headers.get === 'function' ? res.headers.get(name) : null)
  const dbQueries = Number(getHeader('x-debug-db-queries') || 0)
  const dbTime = Number(getHeader('x-debug-db-time-ms') || 0)
  let dbQueryDetails = []
  try {
    const raw = getHeader('x-debug-db-queries-json')
    if (raw) dbQueryDetails = JSON.parse(raw)
  } catch {
    dbQueryDetails = []
  }
  recordApiCall({ method, path, duration, dbQueries, dbTime, dbQueryDetails })
  if (res.status === 204) return null
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new Error((data && data.detail) || res.statusText)
  return data
}

const responseCache = new Map()
const CACHE_TTL_MS = 500

async function request(path, { method = 'GET', body } = {}) {
  const bodyString = body !== undefined ? JSON.stringify(body) : undefined
  if (method !== 'GET') {
    const result = await executeRequest(path, method, body, bodyString)
    responseCache.clear()
    return result
  }
  const key = `${method} ${API + path} ${bodyString || ''}`
  if (pendingRequests.has(key)) {
    return pendingRequests.get(key)
  }
  const cached = responseCache.get(key)
  if (cached && cached.expires > Date.now()) {
    return cached.value
  }

  const run = executeRequest(path, method, body, bodyString)
  pendingRequests.set(key, run)
  run
    .then((data) => {
      responseCache.set(key, { value: data, expires: Date.now() + CACHE_TTL_MS })
    })
    .catch(() => {})
  run.finally(() => pendingRequests.delete(key)).catch(() => {})
  return run
}

export const api = {
  health: () => request('/health'),

  tasks: {
    list: (params = {}) => {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
      return request(`/tasks${qs ? `?${qs}` : ''}`)
    },
    get: (id) => request(`/tasks/${id}`),
    create: (body) => request('/tasks', { method: 'POST', body }),
    bulkUpdate: (body) => request('/tasks/bulk', { method: 'POST', body }),
    update: (id, body) => request(`/tasks/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/tasks/${id}`, { method: 'DELETE' }),
    timeline: (id) => request(`/tasks/${id}/timeline`),
    associate: (id, body) => request(`/tasks/${id}/items`, { method: 'POST', body }),
    unassociate: (id, itemId) => request(`/tasks/${id}/items/${itemId}`, { method: 'DELETE' }),
    dependencies: (id) => request(`/tasks/${id}/dependencies`),
    addDependency: (id, body) => request(`/tasks/${id}/dependencies`, { method: 'POST', body }),
    removeDependency: (id, relatedId) => request(`/tasks/${id}/dependencies/${relatedId}`, { method: 'DELETE' })
  },

  events: {
    list: ({ taskId, type, actor, client, q, before, beforeId, limit } = {}) => {
      const qs = new URLSearchParams()
      if (taskId) qs.set('task_id', taskId)
      if (type) qs.set('type', type)
      if (actor) qs.set('actor', actor)
      if (client) qs.set('client', client)
      if (q) qs.set('q', q)
      if (before) qs.set('before', before)
      if (beforeId) qs.set('before_id', beforeId)
      if (limit) qs.set('limit', String(limit))
      const query = qs.toString()
      return request(`/events${query ? `?${query}` : ''}`)
    },
    sendToSlack: (id, body = {}) => request(`/events/${id}/slack`, { method: 'POST', body }),
    send: (id, body = {}) => request(`/events/${id}/send`, { method: 'POST', body }),
    sendToSlackBulk: (body = {}) => request(`/events/slack`, { method: 'POST', body })
  },

  gantt: {
    get: ({ includeDone = false } = {}) => request(`/gantt${includeDone ? '?include_done=true' : ''}`)
  },

  graph: {
    get: ({ includeDone = false } = {}) => request(`/graph${includeDone ? '?include_done=true' : ''}`)
  },

  tags: {
    list: () => request('/tags')
  },

  stack: {
    list: () => request('/stack'),
    history: () => request('/stack/history'),
    current: () => request('/stack/current'),
    push: (body) => request('/stack', { method: 'POST', body }),
    pop: () => request('/stack/pop', { method: 'POST' }),
    promote: (entryId) => request(`/stack/${entryId}/promote`, { method: 'POST' }),
    reorder: (entryId, position) =>
      request('/stack/reorder', { method: 'POST', body: { entry_id: entryId, position } }),
    update: (entryId, body) => request(`/stack/${entryId}`, { method: 'PATCH', body }),
    remove: (entryId) => request(`/stack/${entryId}`, { method: 'DELETE' })
  },

  people: {
    list: () => request('/people'),
    get: (id) => request(`/people/${id}`),
    create: (body) => request('/people', { method: 'POST', body }),
    update: (id, body) => request(`/people/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/people/${id}`, { method: 'DELETE' }),
    merge: (targetId, sourceId) =>
      request(`/people/${targetId}/merge`, { method: 'POST', body: { source_id: sourceId } }),
    linkTask: (taskId, body) => request(`/tasks/${taskId}/people`, { method: 'POST', body }),
    unlinkTask: (taskId, personId) => request(`/tasks/${taskId}/people/${personId}`, { method: 'DELETE' }),
    linkRequester: (taskId, body) => request(`/tasks/${taskId}/requesters`, { method: 'POST', body }),
    unlinkRequester: (taskId, personId) => request(`/tasks/${taskId}/requesters/${personId}`, { method: 'DELETE' }),
    linkItem: (itemId, body) => request(`/items/${itemId}/people`, { method: 'POST', body }),
    unlinkItem: (itemId, personId) => request(`/items/${itemId}/people/${personId}`, { method: 'DELETE' })
  },

  changes: {
    list: ({ taskId, status, changeClass } = {}) => {
      const qs = new URLSearchParams()
      if (taskId) qs.set('task_id', taskId)
      if (status) qs.set('status', status)
      if (changeClass) qs.set('change_class', changeClass)
      const query = qs.toString()
      return request(`/changes${query ? `?${query}` : ''}`)
    },
    get: (id) => request(`/changes/${id}`),
    create: (body) => request('/changes', { method: 'POST', body }),
    update: (id, body) => request(`/changes/${id}`, { method: 'PATCH', body }),
    transition: (id, status) => request(`/changes/${id}/status`, { method: 'POST', body: { status } }),
    intervene: (id, body) => request(`/changes/${id}/interventions`, { method: 'POST', body }),
    remove: (id) => request(`/changes/${id}`, { method: 'DELETE' })
  },

  inbox: {
    get: () => request('/inbox')
  },

  schedules: {
    list: () => request('/schedules'),
    get: (id) => request(`/schedules/${id}`),
    create: (body) => request('/schedules', { method: 'POST', body }),
    update: (id, body) => request(`/schedules/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/schedules/${id}`, { method: 'DELETE' }),
    run: (id) => request(`/schedules/${id}/run`, { method: 'POST' }),
    runs: (id, limit = 20) => request(`/schedules/${id}/runs?limit=${limit}`),
    executions: (limit = 100) => request(`/schedules/runs?limit=${limit}`),
    preview: (schedule, timezone = '', count = 5) => {
      const params = new URLSearchParams({ schedule, count: String(count) })
      if (timezone) params.set('timezone', timezone)
      return request(`/schedules/preview?${params.toString()}`)
    }
  },

  graphs: {
    list: () => request('/graphs'),
    get: (id) => request(`/graphs/${id}`),
    create: (body) => request('/graphs', { method: 'POST', body }),
    update: (id, body) => request(`/graphs/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/graphs/${id}`, { method: 'DELETE' }),
    run: (id) => request(`/graphs/${id}/run`, { method: 'POST' }),
    validate: (body) => request('/graphs/validate', { method: 'POST', body }),
    executions: (limit = 100) => request(`/graphs/executions?limit=${limit}`),
    execution: (id) => request(`/graphs/executions/${id}`),
    cancelExecution: (id) => request(`/graphs/executions/${id}/cancel`, { method: 'POST' }),
    submitForm: (executionId, nodeId, body) =>
      request(`/graphs/executions/${executionId}/forms/${nodeId}`, { method: 'POST', body })
  },

  reviews: {
    // Every PR with review reports in the user-global store, with its step state.
    // refresh re-reads each PR's GitHub fields instead of the short ghx cache.
    queue: ({ refresh = false } = {}) => request(`/reviews${refresh ? '?refresh=true' : ''}`),
    // The same rows, scoped to the pull requests a task is linked to.
    task: (taskId, { refresh = false } = {}) => request(`/reviews/task/${taskId}${refresh ? '?refresh=true' : ''}`),
    // The must/should/may findings the review skills recorded for one PR.
    findings: (repository, number) =>
      request(`/reviews/findings/${number}?${new URLSearchParams({ repository }).toString()}`),
    // Record the reviewer's include/skip decisions on those findings; the
    // updated list comes back.
    decide: (repository, number, decisions) =>
      request(`/reviews/findings/${number}/decisions`, { method: 'POST', body: { repository, decisions } }),
    // One PR's report, addressed by "owner/name" and its path in the store.
    report: (repository, number, name) =>
      request(
        `/reviews/report/${number}/${String(name).split('/').map(encodeURIComponent).join('/')}` +
          `?${new URLSearchParams({ repository }).toString()}`
      ),
    // The review scan's cadence, its last pass, and how many PRs it holds.
    scan: () => request('/reviews/scan'),
    // Run the scan now, ignoring its cadence.
    runScan: () => request('/reviews/scan', { method: 'POST' })
  },

  feedback: {
    // The reviewer-feedback analysis files in the user-global store, with their
    // decision state. refresh re-reads each PR's GitHub state instead of the
    // short ghx cache.
    list: ({ refresh = false } = {}) => request(`/feedback${refresh ? '?refresh=true' : ''}`),
    // Record a decision (implement/decline/defer), or null to reset it to
    // awaiting a decision, in one analysis file's frontmatter.
    setDecision: (feedbackId, decision) =>
      request(`/feedback/${encodeURIComponent(feedbackId)}/decision`, { method: 'POST', body: { decision } })
  },

  myPulls: {
    // The open pull requests the configured GitHub login authored, with their
    // check rollup, review decision, approvers, and open threads. refresh
    // re-queries GitHub instead of reusing the short cache.
    list: ({ refresh = false } = {}) => request(`/my-pulls${refresh ? '?refresh=true' : ''}`)
  },

  decisions: {
    // The colleague-decisions reports the extract-colleague-decisions skill
    // writes under the notes root, aggregated for the Decisions page.
    list: () => request('/decisions')
  },

  metrics: {
    get: ({ windowDays, observationDays, tolerance, taskId, changeClass } = {}) => {
      const qs = new URLSearchParams()
      if (windowDays) qs.set('window_days', String(windowDays))
      if (observationDays !== undefined && observationDays !== null) qs.set('observation_days', String(observationDays))
      if (tolerance !== undefined && tolerance !== null) qs.set('tolerance', String(tolerance))
      if (taskId) qs.set('task_id', taskId)
      if (changeClass) qs.set('change_class', changeClass)
      const query = qs.toString()
      return request(`/metrics${query ? `?${query}` : ''}`)
    },
    cycleTime: ({ days, bucketDays, repositoryId, refresh } = {}) => {
      const qs = new URLSearchParams()
      if (days) qs.set('days', String(days))
      if (bucketDays) qs.set('bucket_days', String(bucketDays))
      if (repositoryId) qs.set('repository_id', repositoryId)
      if (refresh) qs.set('refresh', 'true')
      const query = qs.toString()
      return request(`/metrics/cycle-time${query ? `?${query}` : ''}`)
    },
    baselines: () => request('/metrics/baselines'),
    setBaseline: (metric, body) => request(`/metrics/baselines/${metric}`, { method: 'PUT', body }),
    removeBaseline: (metric) => request(`/metrics/baselines/${metric}`, { method: 'DELETE' })
  },

  operations: {
    list: ({ client, actor, limit } = {}) => {
      const qs = new URLSearchParams()
      if (client) qs.set('client', client)
      if (actor) qs.set('actor', actor)
      if (limit) qs.set('limit', String(limit))
      const query = qs.toString()
      return request(`/operations${query ? `?${query}` : ''}`)
    }
  },

  items: {
    list: ({ source, q } = {}) => {
      const qs = new URLSearchParams()
      if (source) qs.set('source', source)
      if (q) qs.set('q', q)
      const query = qs.toString()
      return request(`/items${query ? `?${query}` : ''}`)
    },
    get: (id) => request(`/items/${id}`),
    create: (body) => request('/items', { method: 'POST', body }),
    update: (id, body) => request(`/items/${id}`, { method: 'PATCH', body }),
    refresh: (id) => request(`/items/${id}/refresh`, { method: 'POST' }),
    // Read a path item's current file preview or directory listing. Live, and
    // never stored, so it does not go stale between refreshes.
    pathPreview: (id) => request(`/items/${id}/path`),
    refreshSource: (source) => request(`/items/refresh-source/${source}`, { method: 'POST' }),
    reviews: (id) => request(`/items/${id}/reviews`),
    // The reviewers on a PR, one row each, read live from GitHub (gh); a
    // reviewer a review is still requested from comes back as PENDING.
    reviewers: (id) => request(`/items/${id}/reviewers`),
    // Ask a reviewer for their review through a Slack DM. The GitHub login
    // resolves through the people directory to a Slack user id or handle.
    poke: (id, login) => request(`/items/${id}/poke`, { method: 'POST', body: { login } }),
    // The report name is a path relative to the PR's review directory (it may
    // hold a "feedback/" segment), so each segment is encoded separately.
    review: (id, name) => request(`/items/${id}/reviews/${String(name).split('/').map(encodeURIComponent).join('/')}`),
    remove: (id) => request(`/items/${id}`, { method: 'DELETE' })
  },

  repositories: {
    list: () => request('/repositories'),
    create: (body) => request('/repositories', { method: 'POST', body }),
    createBulk: (paths) => request('/repositories/bulk', { method: 'POST', body: { paths } }),
    update: (id, body) => request(`/repositories/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/repositories/${id}`, { method: 'DELETE' })
  },

  fs: {
    list: (path, hidden = false) => {
      const qs = new URLSearchParams()
      if (path) qs.set('path', path)
      if (hidden) qs.set('hidden', 'true')
      const query = qs.toString()
      return request(`/fs/list${query ? `?${query}` : ''}`)
    }
  },

  groups: {
    list: () => request('/groups'),
    create: (body) => request('/groups', { method: 'POST', body }),
    update: (id, body) => request(`/groups/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/groups/${id}`, { method: 'DELETE' })
  },

  github: {
    issues: ({ repository_id, owner, repo, state = 'open', limit = 20 } = {}) => {
      const qs = new URLSearchParams()
      if (repository_id) qs.set('repository_id', repository_id)
      if (owner) qs.set('owner', owner)
      if (repo) qs.set('repo', repo)
      qs.set('state', state)
      qs.set('limit', String(limit))
      return request(`/github/issues?${qs.toString()}`)
    },
    issue: (url) => request(`/github/issue?${new URLSearchParams({ url }).toString()}`),
    createIssue: (body) => request('/github/issues', { method: 'POST', body }),
    repository: ({ repository_id, owner, repo, state = 'all', limit = 1000, refresh = false } = {}) => {
      const qs = new URLSearchParams()
      if (repository_id) qs.set('repository_id', repository_id)
      if (owner) qs.set('owner', owner)
      if (repo) qs.set('repo', repo)
      qs.set('state', state)
      qs.set('limit', String(limit))
      if (refresh) qs.set('refresh', 'true')
      return request(`/github/repository?${qs.toString()}`)
    }
  },

  onCall: {
    scan: (body = {}) => request('/on-call/scan', { method: 'POST', body }),
    list: () => request('/on-call'),
    get: (id) => request(`/on-call/${id}`),
    start: (body = {}) => request('/on-call/start', { method: 'POST', body }),
    stop: (body = {}) => request('/on-call/stop', { method: 'POST', body }),
    threads: (body = {}) => request('/on-call/threads', { method: 'POST', body }),
    replies: (body = {}) => request('/on-call/replies', { method: 'POST', body }),
    reply: (body = {}) => request('/on-call/reply', { method: 'POST', body }),
    send: (body = {}) => request('/on-call/reply', { method: 'POST', body }),
    submit: (body = {}) => request('/on-call/reply', { method: 'POST', body }),
    resolve: (body = {}) => request('/on-call/resolve', { method: 'POST', body })
  },
  oncall: null,
  slack: {
    // Name the Slack user ids given, so a handle like U0123ABCD reads as a name.
    users: (ids = []) => {
      const qs = new URLSearchParams(ids.map((id) => ['ids', id])).toString()
      return request(`/slack/users${qs ? `?${qs}` : ''}`)
    },
    sendEvent: (id, body = {}) => request(`/slack/events/${id}`, { method: 'POST', body }),
    sendEvents: (body = {}) => request(`/slack/events`, { method: 'POST', body }),
    send: (body = {}) => request(`/slack/send`, { method: 'POST', body }),
    test: (body = {}) => request(`/slack/test`, { method: 'POST', body }),
    testNotification: (body = {}) => request(`/slack/test-notification`, { method: 'POST', body })
  },

  harnesses: {
    list: () => request('/harnesses'),
    full: () => request('/harnesses/full'),
    models: (id) => request(`/harnesses/${id}/models`),
    create: (body) => request('/harnesses', { method: 'POST', body }),
    update: (id, body) => request(`/harnesses/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/harnesses/${id}`, { method: 'DELETE' })
  },

  settings: {
    get: () => request('/settings'),
    update: (body) => request('/settings', { method: 'PATCH', body }),
    previewRefreshPolicy: (value) => request('/settings/refresh-policy/preview', { method: 'POST', body: { value } }),
    refreshStatus: () => request('/settings/refresh-status'),
    diagnostics: () => request('/settings/diagnostics'),
    restartTool: (tool) => request(`/settings/tools/${tool}/restart`, { method: 'POST' })
  },

  worktrees: {
    list: (taskId) => request(`/tasks/${taskId}/worktrees`),
    create: (taskId, body) => request(`/tasks/${taskId}/worktrees`, { method: 'POST', body }),
    remove: (taskId, worktreeId) => request(`/tasks/${taskId}/worktrees/${worktreeId}`, { method: 'DELETE' })
  },

  runs: {
    list: (taskId) => request(`/tasks/${taskId}/runs`),
    create: (taskId, body) => request(`/tasks/${taskId}/runs`, { method: 'POST', body }),
    refreshContext: (taskId) => request(`/tasks/${taskId}/context/refresh`, { method: 'POST' }),
    refreshSummary: (taskId) => request(`/tasks/${taskId}/summary/refresh`, { method: 'POST' }),
    context: (taskId) => request(`/tasks/${taskId}/context`),
    get: (runId) => request(`/runs/${runId}`),
    events: (runId) => request(`/runs/${runId}/events`),
    cancel: (runId) => request(`/runs/${runId}/cancel`, { method: 'POST' })
  },

  sessions: {
    list: (taskId) => request(`/tasks/${taskId}/sessions`),
    get: (taskId, sessionId) => request(`/tasks/${taskId}/sessions/${sessionId}`),
    create: (taskId, body) => request(`/tasks/${taskId}/sessions`, { method: 'POST', body }),
    update: (taskId, sessionId, body) => request(`/tasks/${taskId}/sessions/${sessionId}`, { method: 'PATCH', body }),
    remove: (taskId, sessionId) => request(`/tasks/${taskId}/sessions/${sessionId}`, { method: 'DELETE' })
  }
}

export function openRunStream(runId, onEvent, onClose) {
  const es = new EventSource(`${API}/runs/${runId}/stream`)
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
      if (data.type === 'run_finished') {
        es.close()
        onClose && onClose()
      }
    } catch (err) {
      console.warn('bad event', err)
    }
  }
  es.onerror = () => {
    es.close()
    onClose && onClose()
  }
  return () => es.close()
}

export function openTaskStream(taskId, onEvent) {
  const es = new EventSource(`${API}/tasks/${taskId}/stream`)
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch (err) {
      console.warn('bad task event', err)
    }
  }
  return () => es.close()
}
