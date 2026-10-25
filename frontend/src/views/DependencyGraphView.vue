<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Handle, MarkerType, Position, VueFlow } from '@xyflow/vue'
import '@xyflow/vue/dist/style.css'
import '@xyflow/vue/dist/base.css'
import { api } from '../api'
import { layoutGraph, wrapTitle } from '../graph'
import { store } from '../store'

// The Graph page draws the DAG the before/after links form: each task is a node,
// placed in a column by how far it sits along its dependency chain, with an
// arrow from every task to the ones that follow it. Clicking a node opens the
// task. Rendered with Vue Flow (the Vue port of React Flow).
const graph = ref({ nodes: [], edges: [] })
const loading = ref(false)
const error = ref('')
const includeDone = ref(false)
const direction = ref(localStorage.getItem('agentic.graphDirection') || 'LR')
const router = useRouter()
const emit = defineEmits(['changed'])

function toggleDirection() {
  direction.value = direction.value === 'LR' ? 'TB' : 'LR'
  localStorage.setItem('agentic.graphDirection', direction.value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    graph.value = await api.graph.get({ includeDone: includeDone.value })
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const layout = computed(() =>
  layoutGraph(graph.value.nodes, graph.value.edges, { nodeHeight: 56, direction: direction.value })
)

const nodes = computed(() =>
  layout.value.nodes.map((node) => {
    const lines = wrapTitle(node.title)
    return {
      id: node.id,
      position: { x: node.x, y: node.y },
      data: { title: node.title, status: node.status, lines },
      style: { width: `${node.width}px`, height: `${node.height}px` },
      draggable: false,
      selectable: false
    }
  })
)

const edges = computed(() =>
  layout.value.edges.map((edge) => ({
    id: `${edge.before_id}->${edge.after_id}`,
    source: edge.before_id,
    target: edge.after_id,
    type: 'default',
    class: 'dep-edge',
    markerEnd: { type: MarkerType.ArrowClosed, orient: 'auto', color: 'var(--border)' }
  }))
)

function onNodeClick({ event, node }) {
  const target = event?.target
  if (target && (target.closest?.('.vue-flow__handle') || target.classList?.contains('vue-flow__handle'))) return
  router.push(`/task/${node.id}`)
}

async function onConnect({ source, target }) {
  if (!source || !target || source === target) return
  if (graph.value.edges.some((e) => e.before_id === source && e.after_id === target)) return
  try {
    await api.tasks.addDependency(target, { related_id: source, relation: 'before' })
    await load()
    emit('changed')
    store.notify('Linked tasks')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function onEdgeClick({ edge }) {
  if (!edge) return
  try {
    await api.tasks.removeDependency(edge.target, edge.source)
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

function isValidConnection({ source, target }) {
  return !!source && !!target && source !== target
}

const hasGraph = computed(() => graph.value.nodes.length > 0)
const linkedCount = computed(() => graph.value.edges.length)
</script>

<template>
  <div class="page-fill">
    <div class="row page-head" style="margin-bottom: 16px; flex-shrink: 0">
      <h1 class="grow">Graph</h1>
      <span class="faint">{{ graph.nodes.length }} tasks · {{ linkedCount }} links</span>
      <label class="gantt-toggle">
        <input v-model="includeDone" type="checkbox" @change="load" />
        Include done
      </label>
      <button class="btn sm ghost" @click="toggleDirection">
        Layout: {{ direction === 'LR' ? 'Horizontal' : 'Vertical' }}
      </button>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <section class="panel" style="flex: 1; min-height: 0; display: flex; flex-direction: column">
      <div v-if="error" class="empty">
        Couldn't load the graph: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
      </div>
      <div v-else-if="loading && !hasGraph" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!hasGraph" class="empty">No tasks to show. Link a task's dependencies to build the graph.</div>

      <div v-else class="dep-scroll" style="flex: 1; min-height: 220px">
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :nodes-draggable="false"
          :nodes-connectable="true"
          :elements-selectable="true"
          :fit-view="false"
          :is-valid-connection="isValidConnection"
          color-mode="dark"
          style="width: 100%; height: 100%"
          @node-click="onNodeClick"
          @connect="onConnect"
          @edge-click="onEdgeClick"
        >
          <template #node-default="{ id, data }">
            <span class="dep-handle-wrap" @click.stop>
              <Handle type="target" :position="direction === 'LR' ? Position.Left : Position.Top" />
            </span>
            <a :href="`/task/${id}`" class="dep-node-link">
              <div class="dep-node" :class="`st-${data.status}`">
                <span v-for="(line, index) in data.lines" :key="index" class="dep-node-text-line">{{ line }}</span>
              </div>
            </a>
            <span class="dep-handle-wrap" @click.stop>
              <Handle type="source" :position="direction === 'LR' ? Position.Right : Position.Bottom" />
            </span>
          </template>
        </VueFlow>
      </div>
    </section>

    <div v-if="hasGraph" class="dep-legend" style="flex-shrink: 0">
      <span class="legend-item"><span class="dep-dot st-open"></span>open</span>
      <span class="legend-item"><span class="dep-dot st-in_progress"></span>in progress</span>
      <span class="legend-item"><span class="dep-dot st-blocked"></span>blocked</span>
      <span class="legend-item"><span class="dep-dot st-done"></span>done</span>
      <span class="legend-item"><span class="dep-dot st-archived"></span>archived</span>
      <span class="legend-item">arrows point from a task to the ones that follow it</span>
      <span class="legend-item"
        >drag from a node's right handle to another's left to link; click a link to remove it</span
      >
    </div>
  </div>
</template>
