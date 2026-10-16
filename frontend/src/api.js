const API = '/api'

// Every request declares its provenance: the web UI is always a human.
const PROVENANCE_HEADERS = { 'X-Agentic-Client': 'web', 'X-Agentic-Actor': 'human' }

async function request(path, { method = 'GET', body } = {}) {
  const headers = { ...PROVENANCE_HEADERS }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(API + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined
  })
  if (res.status === 204) return null
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new Error((data && data.detail) || res.statusText)
  return data
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
    refreshSource: (source) => request(`/items/refresh-source/${source}`, { method: 'POST' }),
    reviews: (id) => request(`/items/${id}/reviews`),
    // The report name is a path relative to the PR's review directory (it may
    // hold a "feedback/" segment), so each segment is encoded separately.
    review: (id, name) => request(`/items/${id}/reviews/${String(name).split('/').map(encodeURIComponent).join('/')}`),
    remove: (id) => request(`/items/${id}`, { method: 'DELETE' })
  },

  repositories: {
    list: () => request('/repositories'),
    create: (body) => request('/repositories', { method: 'POST', body }),
    createBulk: (paths) => request('/repositories/bulk', { method: 'POST', body: { paths } }),
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

  harnesses: {
    list: () => request('/harnesses'),
    full: () => request('/harnesses/full'),
    create: (body) => request('/harnesses', { method: 'POST', body }),
    update: (id, body) => request(`/harnesses/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/harnesses/${id}`, { method: 'DELETE' })
  },

  settings: {
    get: () => request('/settings'),
    update: (body) => request('/settings', { method: 'PATCH', body }),
    previewRefreshPolicy: (value) => request('/settings/refresh-policy/preview', { method: 'POST', body: { value } }),
    refreshStatus: () => request('/settings/refresh-status')
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
