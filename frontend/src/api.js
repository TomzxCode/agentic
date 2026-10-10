const API = '/api'

async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(API + path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new Error((data && data.detail) || res.statusText)
  return data
}

export const api = {
  health: () => request('/health'),

  problems: {
    list: (params = {}) => {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
      return request(`/problems${qs ? `?${qs}` : ''}`)
    },
    get: (id) => request(`/problems/${id}`),
    create: (body) => request('/problems', { method: 'POST', body }),
    update: (id, body) => request(`/problems/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/problems/${id}`, { method: 'DELETE' }),
    timeline: (id) => request(`/problems/${id}/timeline`),
    associate: (id, body) => request(`/problems/${id}/items`, { method: 'POST', body }),
    unassociate: (id, itemId) => request(`/problems/${id}/items/${itemId}`, { method: 'DELETE' }),
  },

  items: {
    list: (source) => request(`/items${source ? `?source=${source}` : ''}`),
    create: (body) => request('/items', { method: 'POST', body }),
    update: (id, body) => request(`/items/${id}`, { method: 'PATCH', body }),
    refresh: (id) => request(`/items/${id}/refresh`, { method: 'POST' }),
    remove: (id) => request(`/items/${id}`, { method: 'DELETE' }),
  },

  repositories: {
    list: () => request('/repositories'),
    create: (body) => request('/repositories', { method: 'POST', body }),
    createBulk: (paths) => request('/repositories/bulk', { method: 'POST', body: { paths } }),
    remove: (id) => request(`/repositories/${id}`, { method: 'DELETE' }),
  },

  fs: {
    list: (path, hidden = false) => {
      const qs = new URLSearchParams()
      if (path) qs.set('path', path)
      if (hidden) qs.set('hidden', 'true')
      const query = qs.toString()
      return request(`/fs/list${query ? `?${query}` : ''}`)
    },
  },

  harnesses: {
    list: () => request('/harnesses'),
    full: () => request('/harnesses/full'),
    create: (body) => request('/harnesses', { method: 'POST', body }),
    update: (id, body) => request(`/harnesses/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/harnesses/${id}`, { method: 'DELETE' }),
  },

  settings: {
    get: () => request('/settings'),
    update: (body) => request('/settings', { method: 'PATCH', body }),
  },

  worktrees: {
    list: (problemId) => request(`/problems/${problemId}/worktrees`),
    create: (problemId, body) => request(`/problems/${problemId}/worktrees`, { method: 'POST', body }),
    remove: (problemId, worktreeId) =>
      request(`/problems/${problemId}/worktrees/${worktreeId}`, { method: 'DELETE' }),
  },

  runs: {
    list: (problemId) => request(`/problems/${problemId}/runs`),
    create: (problemId, body) => request(`/problems/${problemId}/runs`, { method: 'POST', body }),
    refreshContext: (problemId) => request(`/problems/${problemId}/context/refresh`, { method: 'POST' }),
    context: (problemId) => request(`/problems/${problemId}/context`),
    get: (runId) => request(`/runs/${runId}`),
    events: (runId) => request(`/runs/${runId}/events`),
    cancel: (runId) => request(`/runs/${runId}/cancel`, { method: 'POST' }),
  },
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

export function openProblemStream(problemId, onEvent) {
  const es = new EventSource(`${API}/problems/${problemId}/stream`)
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch (err) {
      console.warn('bad problem event', err)
    }
  }
  return () => es.close()
}
