import { reactive } from 'vue'

const seenRequestIds = new Set()

export const debugStats = reactive({
  apiCalls: 0,
  apiTime: 0,
  dbQueries: 0,
  dbTime: 0,
  lastApiDuration: 0,
  lastDbQueries: 0,
  lastDbTime: 0,
  calls: [],
  requests: [],
  dbRequests: [],
  cliRequests: [],
  cliCalls: [],
  cliQueries: [],
  rpcRequests: [],
  rpcCalls: []
})

export function recordApiCall({
  method = 'GET',
  path = '',
  duration = 0,
  dbQueries = 0,
  dbTime = 0,
  dbQueryDetails = []
} = {}) {
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
  seenRequestIds.clear()
  debugStats.apiCalls = 0
  debugStats.apiTime = 0
  debugStats.dbQueries = 0
  debugStats.dbTime = 0
  debugStats.lastApiDuration = 0
  debugStats.lastDbQueries = 0
  debugStats.lastDbTime = 0
  debugStats.calls = []
  debugStats.requests = []
  debugStats.dbRequests = []
  debugStats.cliRequests = []
  debugStats.cliCalls = debugStats.cliRequests
  debugStats.cliQueries = debugStats.cliRequests
  debugStats.rpcRequests = debugStats.cliRequests
  debugStats.rpcCalls = debugStats.cliRequests
}

export function clearApiCalls() {
  debugStats.requests = []
}

export function clearDbQueries() {
  debugStats.dbRequests = []
}

function clearCliLists() {
  debugStats.cliRequests = []
  debugStats.cliCalls = debugStats.cliRequests
  debugStats.cliQueries = debugStats.cliRequests
  debugStats.rpcRequests = debugStats.cliRequests
  debugStats.rpcCalls = debugStats.cliRequests
}

export function clearCliCalls() {
  clearCliLists()
}

export function clearCliRequests() {
  clearCliLists()
}

export function clearCliQueries() {
  clearCliLists()
}

export function clearRpcCalls() {
  clearCliLists()
}

export function clearRpcRequests() {
  clearCliLists()
}

export async function refreshDebugRequests() {
  try {
    const res = await fetch('/api/debug/requests')
    if (!res.ok) return
    const data = await res.json()
    if (!Array.isArray(data)) return
    // Older servers have no stable IDs, so retain their snapshot behavior.
    if (data.some((request) => !request.id)) {
      debugStats.requests = data
      debugStats.dbRequests = data
      debugStats.cliRequests = data
      debugStats.cliCalls = debugStats.cliRequests
      debugStats.cliQueries = debugStats.cliRequests
      debugStats.rpcRequests = debugStats.cliRequests
      debugStats.rpcCalls = debugStats.cliRequests
      return
    }
    const incoming = data.filter((request) => !seenRequestIds.has(request.id))
    incoming.forEach((request) => seenRequestIds.add(request.id))
    debugStats.requests = [...incoming, ...debugStats.requests]
    debugStats.dbRequests = [...incoming, ...debugStats.dbRequests]
    debugStats.cliRequests = [...incoming, ...debugStats.cliRequests]
    debugStats.cliCalls = debugStats.cliRequests
    debugStats.cliQueries = debugStats.cliRequests
    debugStats.rpcRequests = debugStats.cliRequests
    debugStats.rpcCalls = debugStats.cliRequests
  } catch {
    // ignore
  }
}
