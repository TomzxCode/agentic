import { reactive } from 'vue'

export const debugStats = reactive({
  apiCalls: 0,
  apiTime: 0,
  dbQueries: 0,
  dbTime: 0,
  lastApiDuration: 0,
  lastDbQueries: 0,
  lastDbTime: 0,
  calls: [],
  requests: []
})

export function recordApiCall({ method = 'GET', path = '', duration = 0, dbQueries = 0, dbTime = 0, dbQueryDetails = [] } = {}) {
  debugStats.apiCalls += 1
  debugStats.apiTime += duration
  debugStats.dbQueries += dbQueries
  debugStats.dbTime += dbTime
  debugStats.lastApiDuration = duration
  debugStats.lastDbQueries = dbQueries
  debugStats.lastDbTime = dbTime
  debugStats.calls.push({ method, path, duration, dbQueries, dbTime, dbQueryDetails, at: Date.now() })
  if (debugStats.calls.length > 50) debugStats.calls.shift()
}

export function resetDebugStats() {
  debugStats.apiCalls = 0
  debugStats.apiTime = 0
  debugStats.dbQueries = 0
  debugStats.dbTime = 0
  debugStats.lastApiDuration = 0
  debugStats.lastDbQueries = 0
  debugStats.lastDbTime = 0
  debugStats.calls = []
  debugStats.requests = []
}

export async function refreshDebugRequests() {
  try {
    const res = await fetch('/api/debug/requests')
    if (!res.ok) return
    const data = await res.json()
    debugStats.requests = Array.isArray(data) ? data : []
  } catch {
    // ignore
  }
}