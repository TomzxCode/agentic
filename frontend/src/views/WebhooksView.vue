<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import EntityCard from '../components/EntityCard.vue'
import { formatDateTime, store } from '../store'

// The webhooks page: the entry points an outside system posts to, the
// execution-graph workflows each one feeds, and the deliveries that arrived.
// An event starts every matching workflow, whose trigger node reads the payload.
const tab = ref('endpoints')
const loading = ref(true)
const eventsLoading = ref(false)
const busy = ref('')
const endpoints = ref([])
const events = ref([])
const graphs = ref([])

const creating = ref(false)
const newEndpoint = ref(blankEndpoint())
const editing = ref('')
const editDraft = ref({})
const openWorkflows = ref('')
const subscriptions = ref([])
const subscriptionsLoading = ref(false)
const subDraft = ref(blankSubscription())
const openedEvent = ref('')
const eventDetail = ref(null)
const eventDetailLoading = ref(false)

const triggerHint = computed(() => {
  if (!graphs.value.length) return 'Create an execution graph first, with an Event trigger step.'
  return 'A workflow starts when the event matches its subscription.'
})

function blankEndpoint() {
  return { name: '', description: '', kind: 'generic', secret: '', enabled: true }
}

function blankSubscription() {
  return { graph_id: '', name: '', events: '', filters: [], enabled: true }
}

function blankFilter() {
  return { path: '', operator: 'equals', value: '' }
}

function hookUrl(endpoint) {
  const base = `${window.location.origin}/api/hooks`
  return endpoint.kind === 'github' ? `${base}/github/${endpoint.id}` : `${base}/${endpoint.id}`
}

function eventLabel(endpoint) {
  return endpoint.kind === 'github' ? 'GitHub' : 'Generic'
}

function graphLabel(graph) {
  const nodes = graph.definition?.nodes || []
  const suffix = nodes.some((node) => node.kind === 'trigger') ? '' : ' (no event trigger)'
  return `${graph.name}${suffix}`
}

function refreshAll() {
  load()
  loadEvents()
}

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    endpoints.value = await api.webhooks.endpoints()
  } catch (e) {
    if (!silent) store.notify(e.message, true)
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadEvents({ silent = false } = {}) {
  if (!silent) eventsLoading.value = true
  try {
    events.value = await api.webhooks.events({ limit: 50 })
  } catch (e) {
    if (!silent) store.notify(e.message, true)
  } finally {
    if (!silent) eventsLoading.value = false
  }
}

async function loadGraphs() {
  try {
    graphs.value = await api.graphs.list()
  } catch {
    // The subscription form simply has no workflow choices.
  }
}

onMounted(() => {
  load()
  loadEvents()
  loadGraphs()
})

function cancelCreate() {
  creating.value = false
  newEndpoint.value = blankEndpoint()
}

async function createEndpoint() {
  busy.value = 'new'
  try {
    await api.webhooks.createEndpoint({
      ...newEndpoint.value,
      name: newEndpoint.value.name.trim(),
      description: newEndpoint.value.description.trim(),
      secret: newEndpoint.value.secret.trim()
    })
    creating.value = false
    newEndpoint.value = blankEndpoint()
    await load({ silent: true })
    store.notify('Webhook endpoint created')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

function openEdit(endpoint) {
  editing.value = endpoint.id
  editDraft.value = {
    name: endpoint.name,
    description: endpoint.description || '',
    kind: endpoint.kind,
    secret: endpoint.secret || '',
    enabled: endpoint.enabled
  }
}

function cancelEdit() {
  editing.value = ''
  editDraft.value = {}
}

async function saveEdit(endpoint) {
  busy.value = endpoint.id
  try {
    await api.webhooks.updateEndpoint(endpoint.id, {
      name: editDraft.value.name.trim(),
      description: editDraft.value.description.trim(),
      kind: editDraft.value.kind,
      secret: editDraft.value.secret.trim(),
      enabled: editDraft.value.enabled
    })
    cancelEdit()
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function toggleEnabled(endpoint) {
  busy.value = endpoint.id
  try {
    await api.webhooks.updateEndpoint(endpoint.id, { enabled: !endpoint.enabled })
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function removeEndpoint(endpoint) {
  if (!window.confirm(`Delete '${endpoint.name}', its workflows, and its stored events?`)) return
  busy.value = endpoint.id
  try {
    await api.webhooks.removeEndpoint(endpoint.id)
    if (openWorkflows.value === endpoint.id) openWorkflows.value = ''
    await load({ silent: true })
    await loadEvents({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function testEndpoint(endpoint) {
  busy.value = endpoint.id
  try {
    const result = await api.webhooks.test(endpoint.id, { event_type: 'test', payload: { action: 'test' } })
    store.notify(`Sent a test event: ${(result.deliveries || []).length} workflow(s) started`)
    await load({ silent: true })
    await loadEvents({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function copyUrl(endpoint) {
  try {
    await navigator.clipboard.writeText(hookUrl(endpoint))
    store.notify('Webhook URL copied')
  } catch {
    store.notify('Could not copy the URL', true)
  }
}

async function toggleWorkflows(endpoint) {
  if (openWorkflows.value === endpoint.id) {
    openWorkflows.value = ''
    subscriptions.value = []
    return
  }
  openWorkflows.value = endpoint.id
  subDraft.value = blankSubscription()
  await loadSubscriptions(endpoint.id)
}

async function loadSubscriptions(endpointId) {
  subscriptionsLoading.value = true
  try {
    subscriptions.value = await api.webhooks.subscriptions(endpointId)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    subscriptionsLoading.value = false
  }
}

function addFilter() {
  subDraft.value.filters.push(blankFilter())
}

function removeFilter(index) {
  subDraft.value.filters.splice(index, 1)
}

function apiFilters(filters) {
  return (filters || [])
    .filter((condition) => condition.path.trim())
    .map((condition) => {
      if (condition.operator === 'exists') {
        return { path: condition.path.trim(), exists: condition.value !== 'false' }
      }
      return { path: condition.path.trim(), [condition.operator]: condition.value }
    })
}

async function addSubscription() {
  const endpointId = openWorkflows.value
  if (!endpointId) return
  if (!subDraft.value.graph_id) {
    store.notify('Pick a workflow', true)
    return
  }
  busy.value = 'subscribe'
  try {
    await api.webhooks.createSubscription(endpointId, {
      graph_id: subDraft.value.graph_id,
      name: subDraft.value.name.trim(),
      events: subDraft.value.events
        .split(',')
        .map((event) => event.trim())
        .filter(Boolean),
      filters: apiFilters(subDraft.value.filters),
      enabled: subDraft.value.enabled
    })
    subDraft.value = blankSubscription()
    await loadSubscriptions(endpointId)
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function toggleSubscription(subscription) {
  busy.value = subscription.id
  try {
    await api.webhooks.updateSubscription(subscription.id, { enabled: !subscription.enabled })
    await loadSubscriptions(openWorkflows.value)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function removeSubscription(subscription) {
  if (!window.confirm(`Remove the workflow '${subscription.graph_name || subscription.graph_id}'?`)) return
  busy.value = subscription.id
  try {
    await api.webhooks.removeSubscription(subscription.id)
    await loadSubscriptions(openWorkflows.value)
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function toggleEvent(event) {
  if (openedEvent.value === event.id) {
    openedEvent.value = ''
    eventDetail.value = null
    return
  }
  openedEvent.value = event.id
  eventDetailLoading.value = true
  try {
    eventDetail.value = await api.webhooks.event(event.id)
  } catch (e) {
    store.notify(e.message, true)
    eventDetail.value = null
  } finally {
    eventDetailLoading.value = false
  }
}

async function replayEvent(event) {
  busy.value = event.id
  try {
    const result = await api.webhooks.replay(event.id)
    store.notify(`Replayed: ${(result.deliveries || []).length} delivery(s)`)
    await loadEvents({ silent: true })
    if (openedEvent.value === event.id) eventDetail.value = await api.webhooks.event(event.id)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Webhooks</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span class="faint">
          {{
            tab === 'endpoints'
              ? `${endpoints.length} endpoint${endpoints.length === 1 ? '' : 's'}`
              : `${events.length} event${events.length === 1 ? '' : 's'}`
          }}
        </span>
        <button class="btn sm ghost" :disabled="loading || eventsLoading" @click="refreshAll">Refresh</button>
      </span>
    </div>

    <p class="faint" style="margin: 0 0 12px">
      Point a service at an endpoint, wire an execution graph to it, and every matching event starts that workflow. A
      graph's Event trigger step exposes payload fields to its steps.
    </p>

    <div class="row webhook-tabs" role="tablist" aria-label="Webhook views">
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'endpoints' }"
        role="tab"
        :aria-selected="tab === 'endpoints'"
        @click="tab = 'endpoints'"
      >
        Endpoints
      </button>
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'events' }"
        role="tab"
        :aria-selected="tab === 'events'"
        @click="tab = 'events'"
      >
        Events
      </button>
    </div>

    <template v-if="tab === 'endpoints'">
      <div v-if="creating" class="panel panel-form" style="margin-bottom: 12px">
        <h2>New webhook endpoint</h2>
        <div class="field">
          <label for="hook-name">Name</label>
          <input id="hook-name" v-model="newEndpoint.name" class="input" placeholder="GitHub pull requests" />
        </div>
        <div class="field">
          <label for="hook-kind">Kind</label>
          <select id="hook-kind" v-model="newEndpoint.kind" class="input">
            <option value="generic">Generic JSON webhook</option>
            <option value="github">GitHub webhook</option>
          </select>
        </div>
        <div class="field">
          <label for="hook-description">Description</label>
          <input id="hook-description" v-model="newEndpoint.description" class="input" />
        </div>
        <div class="field">
          <label for="hook-secret">Secret</label>
          <input
            id="hook-secret"
            v-model="newEndpoint.secret"
            class="input"
            type="password"
            autocomplete="new-password"
          />
          <p class="faint" style="margin: 4px 0 0">
            On a GitHub endpoint this is the webhook secret, used to verify every signature. On a generic endpoint it is
            an optional token the sender must present in <code>X-Webhook-Secret</code> or as a bearer token.
          </p>
        </div>
        <div class="row" style="gap: 8px">
          <button class="btn sm primary" :disabled="busy === 'new'" @click="createEndpoint">Create endpoint</button>
          <button class="btn sm ghost" @click="cancelCreate">Cancel</button>
        </div>
      </div>

      <div v-if="!loading && !endpoints.length && !creating" class="empty">
        <p class="faint">No webhook endpoints yet.</p>
        <button class="btn primary" @click="creating = true">New endpoint</button>
      </div>

      <div class="webhook-list">
        <div v-for="endpoint in endpoints" :key="endpoint.id">
          <EntityCard>
            <template #lead>
              <span class="badge">{{ eventLabel(endpoint) }}</span>
            </template>
            <template #title>
              <strong>{{ endpoint.name }}</strong>
            </template>
            <template #title-extra>
              <span v-if="!endpoint.enabled" class="badge webhook-paused">paused</span>
            </template>
            <template #actions>
              <span class="row" style="gap: 6px">
                <button class="btn sm ghost" :disabled="busy === endpoint.id" @click="testEndpoint(endpoint)">
                  Test
                </button>
                <button class="btn sm ghost" @click="toggleWorkflows(endpoint)">
                  Workflows ({{ endpoint.subscription_count || 0 }})
                </button>
                <button class="btn sm ghost" @click="toggleEnabled(endpoint)">
                  {{ endpoint.enabled ? 'Pause' : 'Resume' }}
                </button>
                <button class="btn sm ghost" @click="openEdit(endpoint)">Edit</button>
                <button class="btn sm ghost" :disabled="busy === endpoint.id" @click="removeEndpoint(endpoint)">
                  Delete
                </button>
              </span>
            </template>

            <p v-if="endpoint.description" class="faint" style="margin: 2px 0 0">{{ endpoint.description }}</p>
            <p class="hook-url-line">
              <code class="hook-url">{{ hookUrl(endpoint) }}</code>
              <button class="btn sm ghost" @click="copyUrl(endpoint)">Copy URL</button>
            </p>
            <p class="faint" style="margin: 2px 0 0; font-size: 12px">
              {{ endpoint.subscription_count }} workflow(s) · {{ endpoint.event_count }} stored event(s) · secret
              {{ endpoint.secret ? 'set' : 'not set' }}
            </p>

            <div v-if="editing === endpoint.id" class="panel panel-form" style="margin-top: 10px">
              <div class="field">
                <label :for="`edit-name-${endpoint.id}`">Name</label>
                <input :id="`edit-name-${endpoint.id}`" v-model="editDraft.name" class="input" />
              </div>
              <div class="field">
                <label :for="`edit-kind-${endpoint.id}`">Kind</label>
                <select :id="`edit-kind-${endpoint.id}`" v-model="editDraft.kind" class="input">
                  <option value="generic">Generic JSON webhook</option>
                  <option value="github">GitHub webhook</option>
                </select>
              </div>
              <div class="field">
                <label :for="`edit-description-${endpoint.id}`">Description</label>
                <input :id="`edit-description-${endpoint.id}`" v-model="editDraft.description" class="input" />
              </div>
              <div class="field">
                <label :for="`edit-secret-${endpoint.id}`">Secret</label>
                <input
                  :id="`edit-secret-${endpoint.id}`"
                  v-model="editDraft.secret"
                  class="input"
                  type="password"
                  autocomplete="new-password"
                />
              </div>
              <label class="row" style="gap: 6px; align-items: center">
                <input v-model="editDraft.enabled" type="checkbox" />
                <span>Accept events</span>
              </label>
              <div class="row" style="gap: 8px; margin-top: 8px">
                <button class="btn sm primary" :disabled="busy === endpoint.id" @click="saveEdit(endpoint)">
                  Save
                </button>
                <button class="btn sm ghost" @click="cancelEdit">Cancel</button>
              </div>
            </div>

            <div v-if="openWorkflows === endpoint.id" class="panel panel-form" style="margin-top: 10px">
              <h3 style="margin-top: 0">Workflows</h3>
              <p class="faint" style="margin: 0 0 8px">{{ triggerHint }}</p>
              <p v-if="subscriptionsLoading" class="faint">Loading…</p>
              <div v-for="subscription in subscriptions" :key="subscription.id" class="item webhook-subscription">
                <div class="grow" style="min-width: 0">
                  <strong>{{ subscription.name || subscription.graph_name || subscription.graph_id }}</strong>
                  <span v-if="!subscription.enabled" class="badge webhook-paused" style="margin-left: 6px">paused</span>
                  <p class="faint" style="margin: 2px 0 0; font-size: 12px">
                    {{ subscription.graph_name || subscription.graph_id }} ·
                    {{ (subscription.events || []).join(', ') || 'all event types' }}
                    <template v-if="(subscription.filters || []).length">
                      ·
                      {{
                        subscription.filters
                          .map(
                            (condition) => `${condition.path} ${Object.keys(condition).find((key) => key !== 'path')}`
                          )
                          .join(', ')
                      }}
                    </template>
                  </p>
                </div>
                <span class="row" style="gap: 6px">
                  <button
                    class="btn sm ghost"
                    :disabled="busy === subscription.id"
                    @click="toggleSubscription(subscription)"
                  >
                    {{ subscription.enabled ? 'Pause' : 'Resume' }}
                  </button>
                  <button
                    class="btn sm ghost"
                    :disabled="busy === subscription.id"
                    @click="removeSubscription(subscription)"
                  >
                    Remove
                  </button>
                </span>
              </div>
              <p v-if="!subscriptionsLoading && !subscriptions.length" class="faint">No workflow is wired yet.</p>

              <div class="webhook-subscribe">
                <div class="field">
                  <label :for="`sub-graph-${endpoint.id}`">Workflow</label>
                  <select :id="`sub-graph-${endpoint.id}`" v-model="subDraft.graph_id" class="input">
                    <option value="">Pick an execution graph…</option>
                    <option v-for="graph in graphs" :key="graph.id" :value="graph.id">
                      {{ graphLabel(graph) }}
                    </option>
                  </select>
                </div>
                <div class="field">
                  <label :for="`sub-name-${endpoint.id}`">Label (optional)</label>
                  <input :id="`sub-name-${endpoint.id}`" v-model="subDraft.name" class="input" />
                </div>
                <div class="field">
                  <label :for="`sub-events-${endpoint.id}`">Event types (comma separated, empty for all)</label>
                  <input
                    :id="`sub-events-${endpoint.id}`"
                    v-model="subDraft.events"
                    class="input"
                    placeholder="pull_request, issues"
                  />
                </div>
                <div class="field">
                  <span>Payload filters</span>
                  <div v-for="(condition, index) in subDraft.filters" :key="index" class="row webhook-filter-row">
                    <input v-model="condition.path" class="input" placeholder="action" :aria-label="`Filter path`" />
                    <select v-model="condition.operator" class="input" :aria-label="`Filter operator`">
                      <option value="equals">equals</option>
                      <option value="contains">contains</option>
                      <option value="exists">exists</option>
                    </select>
                    <input v-model="condition.value" class="input" placeholder="opened" :aria-label="`Filter value`" />
                    <button class="btn sm ghost" @click="removeFilter(index)">×</button>
                  </div>
                  <button class="btn sm" style="margin-top: 6px" @click="addFilter">+ Filter</button>
                </div>
                <button class="btn sm primary" :disabled="busy === 'subscribe'" @click="addSubscription">
                  Wire workflow
                </button>
              </div>
            </div>
          </EntityCard>
        </div>

        <div v-if="!loading && endpoints.length" class="row" style="margin-top: 10px">
          <button class="btn sm" @click="creating = true">New endpoint</button>
        </div>
      </div>
    </template>

    <template v-else>
      <div v-if="!eventsLoading && !events.length" class="empty">
        <p class="faint">No events received yet.</p>
      </div>
      <div class="webhook-list">
        <EntityCard v-for="event in events" :key="event.id">
          <template #lead>
            <span class="badge">{{ event.event_type }}</span>
          </template>
          <template #title>
            <strong>{{ event.endpoint_name || event.endpoint_id }}</strong>
          </template>
          <template #actions>
            <span class="row" style="gap: 6px">
              <button class="btn sm ghost" @click="toggleEvent(event)">
                {{ openedEvent === event.id ? 'Hide payload' : 'Payload' }}
              </button>
              <button class="btn sm ghost" :disabled="busy === event.id" @click="replayEvent(event)">Replay</button>
            </span>
          </template>
          <p class="faint" style="margin: 2px 0 0; font-size: 12px">
            {{ formatDateTime(event.created_at) }} · {{ event.delivery_count }} delivery(s)
            <template v-if="event.delivery_id"> · delivery {{ event.delivery_id }}</template>
          </p>
          <div v-if="openedEvent === event.id" class="webhook-payload">
            <p v-if="eventDetailLoading" class="faint">Loading…</p>
            <template v-else-if="eventDetail">
              <pre>{{ JSON.stringify(eventDetail.payload, null, 2) }}</pre>
              <div v-for="delivery in eventDetail.deliveries" :key="delivery.id" class="webhook-delivery">
                <span
                  class="badge"
                  :class="{
                    ok: delivery.status === 'started',
                    danger: delivery.status === 'failed',
                    warn: delivery.status === 'skipped'
                  }"
                >
                  {{ delivery.status }}
                </span>
                {{ delivery.graph_name || delivery.graph_id }}
                <span v-if="delivery.graph_execution_id" class="faint"
                  >→ execution {{ delivery.graph_execution_id }}</span
                >
                <span v-if="delivery.error" class="faint"> · {{ delivery.error }}</span>
              </div>
              <p v-if="!eventDetail.deliveries.length" class="faint">No workflow matched this event.</p>
            </template>
          </div>
        </EntityCard>
      </div>
    </template>
  </div>
</template>

<style scoped>
.webhook-tabs {
  gap: 6px;
  margin-bottom: 12px;
}
.webhook-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hook-url-line {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin: 6px 0 0;
  font-size: 12px;
}
.hook-url {
  overflow-wrap: anywhere;
}
.webhook-paused {
  color: var(--warn);
  border: 1px solid var(--warn);
  text-transform: none;
}
.webhook-subscription {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.webhook-subscribe {
  border-top: 1px solid var(--border);
  margin-top: 10px;
  padding-top: 10px;
}
.webhook-filter-row {
  gap: 6px;
  margin-top: 6px;
  align-items: center;
}
.webhook-payload {
  margin-top: 8px;
}
.webhook-payload pre {
  max-height: 320px;
  overflow: auto;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
  font-size: 12px;
}
.webhook-delivery {
  margin-top: 6px;
  font-size: 13px;
}
.panel-form {
  padding: 12px;
}
@media (max-width: 760px) {
  .webhook-filter-row {
    flex-wrap: wrap;
  }
}
</style>
