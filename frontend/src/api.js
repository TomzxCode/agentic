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

  tasks: {
    list: (params = {}) => {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
      return request(`/tasks${qs ? `?${qs}` : ''}`)
    },
    get: (id) => request(`/tasks/${id}`),
    create: (body) => request('/tasks', { method: 'POST', body }),
    update: (id, body) => request(`/tasks/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/tasks/${id}`, { method: 'DELETE' }),
    timeline: (id) => request(`/tasks/${id}/timeline`),
    associate: (id, body) => request(`/tasks/${id}/items`, { method: 'POST', body }),
    unassociate: (id, itemId) => request(`/tasks/${id}/items/${itemId}`, { method: 'DELETE' }),
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

  groups: {
    list: () => request('/groups'),
    create: (body) => request('/groups', { method: 'POST', body }),
    update: (id, body) => request(`/groups/${id}`, { method: 'PATCH', body }),
    remove: (id) => request(`/groups/${id}`, { method: 'DELETE' }),
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
    list: (taskId) => request(`/tasks/${taskId}/worktrees`),
    create: (taskId, body) => request(`/tasks/${taskId}/worktrees`, { method: 'POST', body }),
    remove: (taskId, worktreeId) =>
      request(`/tasks/${taskId}/worktrees/${worktreeId}`, { method: 'DELETE' }),
  },

  runs: {
    list: (taskId) => request(`/tasks/${taskId}/runs`),
    create: (taskId, body) => request(`/tasks/${taskId}/runs`, { method: 'POST', body }),
    refreshContext: (taskId) => request(`/tasks/${taskId}/context/refresh`, { method: 'POST' }),
    context: (taskId) => request(`/tasks/${taskId}/context`),
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
