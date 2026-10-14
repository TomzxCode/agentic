<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { edgePath, layoutGraph, wrapTitle } from '../graph'
import { store } from '../store'

// The Graph page draws the DAG the before/after links form: each task is a node,
// placed in a column by how far it sits along its dependency chain, with an
// arrow from every task to the ones that follow it. Clicking a node opens the
// task.
const graph = ref({ nodes: [], edges: [] })
const loading = ref(false)
const error = ref('')
const includeDone = ref(false)

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

const layout = computed(() => layoutGraph(graph.value.nodes, graph.value.edges))

// Resolve each edge to its curve and each node to its wrapped title, so the
// template stays declarative.
const view = computed(() => {
  const byId = new Map(layout.value.nodes.map((node) => [node.id, node]))
  return {
    nodes: layout.value.nodes.map((node) => {
      const lines = wrapTitle(node.title)
      return {
        ...node,
        lines,
        textY: node.y + node.height / 2 - ((lines.length - 1) * 14) / 2 + 5
      }
    }),
    edges: layout.value.edges
      .map((edge) => ({ ...edge, d: edgePath(byId.get(edge.before_id), byId.get(edge.after_id)) }))
      .filter((edge) => edge.d)
  }
})

const hasGraph = computed(() => graph.value.nodes.length > 0)
const linkedCount = computed(() => graph.value.edges.length)
</script>

<template>
  <div>
    <div class="row page-head" style="margin-bottom: 16px">
      <h1 class="grow">Graph</h1>
      <span class="faint">{{ graph.nodes.length }} tasks · {{ linkedCount }} links</span>
      <label class="gantt-toggle">
        <input v-model="includeDone" type="checkbox" @change="load" />
        Include done
      </label>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <section class="panel">
      <div v-if="error" class="empty">
        Couldn't load the graph: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
      </div>
      <div v-else-if="loading && !hasGraph" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!hasGraph" class="empty">No tasks to show. Link a task's dependencies to build the graph.</div>

      <div v-else class="dep-scroll">
        <svg
          class="dep-svg"
          :width="layout.width"
          :height="layout.height"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
        >
          <defs>
            <marker id="dep-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" class="dep-arrowhead" />
            </marker>
          </defs>

          <path
            v-for="(edge, index) in view.edges"
            :key="index"
            :d="edge.d"
            class="dep-edge"
            marker-end="url(#dep-arrow)"
          />

          <a v-for="node in view.nodes" :key="node.id" :href="`/task/${node.id}`" class="dep-node-link">
            <title>{{ node.title }}</title>
            <rect
              :x="node.x"
              :y="node.y"
              :width="node.width"
              :height="node.height"
              rx="8"
              class="dep-node"
              :class="`st-${node.status}`"
            />
            <text :x="node.x + 12" :y="node.textY" class="dep-node-text">
              <tspan v-for="(line, index) in node.lines" :key="index" :x="node.x + 12" :dy="index === 0 ? 0 : 14">
                {{ line }}
              </tspan>
            </text>
          </a>
        </svg>
      </div>
    </section>

    <div v-if="hasGraph" class="dep-legend">
      <span class="legend-item"><span class="dep-dot st-open"></span>open</span>
      <span class="legend-item"><span class="dep-dot st-in_progress"></span>in progress</span>
      <span class="legend-item"><span class="dep-dot st-blocked"></span>blocked</span>
      <span class="legend-item"><span class="dep-dot st-done"></span>done</span>
      <span class="legend-item"><span class="dep-dot st-archived"></span>archived</span>
      <span class="legend-item">arrows point from a task to the ones that follow it</span>
    </div>
  </div>
</template>
