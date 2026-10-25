<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NODE_WIDTH,
  HEADER_HEIGHT,
  ROW_HEIGHT,
  FIELD_TYPES,
  autoLayout,
  blankField,
  blankFormNode,
  blankInput,
  blankRunNode,
  canvasSize,
  connect,
  dropDanglingEdges,
  edgeEndpoints,
  edgePath,
  editorIssues,
  nodeRows,
  normalizeDefinition,
  portPoint,
  removeField,
  removeInput,
  removeNode
} from '../executionGraph'

// The drag-and-drop canvas for one graph's definition: nodes are cards you
// drag, ports wire into each other, and the inspector edits the selected node.
// The definition lives here as the draft; saving hands it to the parent, which
// sends it to the server (the authority on validity).
const props = defineProps({
  graph: { type: Object, required: true },
  harnesses: { type: Array, default: () => [] }
})
const emit = defineEmits(['save', 'close', 'run'])

const definition = ref(autoLayout(normalizeDefinition(props.graph.definition)))
const selected = ref('')
const selectedEdge = ref('')
// A connection being drawn: where it starts and where the pointer is now.
const pending = ref(null)
// The node being dragged, with the grab offset inside the card.
const dragging = ref(null)
const issues = ref([])
const saving = ref(false)
const content = ref(null)

const size = computed(() => canvasSize(definition.value))
const issueSet = computed(() => new Set(issues.value))
const selectedNode = computed(() => definition.value.nodes.find((node) => node.id === selected.value) || null)

const edges = computed(() =>
  definition.value.edges
    .map((edge) => ({ edge, points: edgeEndpoints(definition.value, edge) }))
    .filter((entry) => entry.points)
)

function nodeById(id) {
  return definition.value.nodes.find((node) => node.id === id)
}

function addNode(kind) {
  const node = kind === 'form' ? blankFormNode() : blankRunNode()
  // Drop new nodes where the canvas is scrolled to, stepping each one down so
  // consecutive additions do not stack on top of each other.
  const box = content.value?.parentElement
  const step = definition.value.nodes.length * 28
  node.position = { x: (box?.scrollLeft || 0) + 60 + step, y: (box?.scrollTop || 0) + 60 + step }
  definition.value.nodes.push(node)
  selected.value = node.id
  selectedEdge.value = ''
}
function selectNode(id) {
  selected.value = id
  selectedEdge.value = ''
}

function selectEdge(id) {
  selectedEdge.value = id
  selected.value = ''
}

function deleteSelected() {
  if (selectedEdge.value) {
    definition.value.edges = definition.value.edges.filter((edge) => edge.id !== selectedEdge.value)
    selectedEdge.value = ''
    return
  }
  if (!selected.value) return
  definition.value = dropDanglingEdges(removeNode(definition.value, selected.value))
  selected.value = ''
}

function startDrag(event, node) {
  if (event.button !== 0 && event.pointerType === 'mouse') return
  // Ports and controls handle their own events; only the card body drags.
  if (event.target.closest('[data-port], button, input, textarea, select, label')) return
  selectNode(node.id)
  const box = content.value.getBoundingClientRect()
  dragging.value = {
    id: node.id,
    dx: event.clientX - box.left - node.position.x,
    dy: event.clientY - box.top - node.position.y
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event) {
  if (dragging.value) {
    const box = content.value.getBoundingClientRect()
    const node = nodeById(dragging.value.id)
    if (node) {
      node.position = {
        x: Math.max(0, event.clientX - box.left - dragging.value.dx),
        y: Math.max(0, event.clientY - box.top - dragging.value.dy)
      }
    }
    return
  }
  if (pending.value) {
    const box = content.value.getBoundingClientRect()
    pending.value.x = event.clientX - box.left
    pending.value.y = event.clientY - box.top
  }
}

function onPointerUp(event) {
  if (dragging.value) {
    dragging.value = null
    return
  }
  if (!pending.value) return
  // Land on whatever port is under the pointer, if any.
  const landing = document.elementFromPoint(event.clientX, event.clientY)
  const drop = landing?.closest('[data-port-kind][data-node-id]')
  if (drop) {
    const port = { kind: drop.dataset.portKind, id: drop.dataset.portId }
    definition.value = connect(
      definition.value,
      pending.value.sourceId,
      pending.value.sourceFieldId,
      drop.dataset.nodeId,
      port
    )
  }
  pending.value = null
}

function startConnect(event, node, row) {
  event.stopPropagation()
  const point = portPoint(node, row)
  pending.value = {
    sourceId: node.id,
    sourceFieldId: row.kind === 'field' ? row.id : '',
    startX: point.x,
    startY: point.y,
    x: point.x,
    y: point.y
  }
  onPointerMove(event)
}

function rowsFor(node) {
  return nodeRows(node)
}

function onCanvasBackground(event) {
  if (event.target.closest('[data-node-card], button, input, textarea, select')) return
  selected.value = ''
  selectedEdge.value = ''
}

function onKeyDown(event) {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
  if ((event.key === 'Delete' || event.key === 'Backspace') && !typing && (selected.value || selectedEdge.value)) {
    event.preventDefault()
    deleteSelected()
  }
  if (event.key === 'Escape') pending.value = null
}

// --- inspector edits --------------------------------------------------------
function addInput(node) {
  node.inputs.push(blankInput(`input${node.inputs.length + 1}`))
}

function removeNodeInput(node, inputId) {
  const index = definition.value.nodes.findIndex((candidate) => candidate.id === node.id)
  if (index === -1) return
  definition.value.nodes[index] = removeInput(node, inputId)
  definition.value = dropDanglingEdges(definition.value)
}

function addField(node) {
  node.fields.push(blankField())
}

function removeNodeField(node, fieldId) {
  const index = definition.value.nodes.findIndex((candidate) => candidate.id === node.id)
  if (index === -1) return
  definition.value.nodes[index] = removeField(node, fieldId)
  definition.value = dropDanglingEdges(definition.value)
}

// --- actions ----------------------------------------------------------------
async function validate() {
  issues.value = editorIssues(definition.value)
  try {
    const { api } = await import('../api')
    const remote = await api.graphs.validate({ name: props.graph.name, definition: definition.value })
    for (const issue of remote.issues || []) {
      if (!issues.value.includes(issue)) issues.value.push(issue)
    }
  } catch {
    // The local issues still show; the server repeats them at save time.
  }
}

async function save() {
  issues.value = editorIssues(definition.value)
  if (issues.value.length) return
  saving.value = true
  try {
    await emit('save', JSON.parse(JSON.stringify(definition.value)))
  } finally {
    saving.value = false
  }
}

// Run asks the parent to persist this draft first and start the graph, so the
// execution uses exactly what is on screen.
function run() {
  issues.value = editorIssues(definition.value)
  if (issues.value.length) return
  emit('run', JSON.parse(JSON.stringify(definition.value)))
}

onMounted(() => {
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('keydown', onKeyDown)
})
onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <div class="panel editor-panel">
    <div class="panel-head">
      <h2>{{ graph.name }}</h2>
      <span class="row" style="gap: 6px; flex-wrap: wrap">
        <button class="btn sm" @click="addNode('run')">+ Run step</button>
        <button class="btn sm" @click="addNode('form')">+ Form step</button>
        <button class="btn sm" @click="validate">Check</button>
        <button class="btn sm primary" :disabled="saving || issueSet.size > 0" @click="save">Save</button>
        <button class="btn sm" :disabled="issueSet.size > 0" @click="run">Run</button>
        <button class="btn sm ghost" @click="emit('close')">Close</button>
      </span>
    </div>

    <p v-if="issues.length" class="editor-issues">
      <span v-for="issue in issues" :key="issue">{{ issue }}</span>
    </p>
    <p v-else class="faint editor-hint">
      Drag cards to arrange them. Drag from a right-side dot onto an input or a form field to connect. Select something
      and press Delete to remove it.
    </p>

    <div class="editor-body">
      <div class="editor-canvas" @pointerdown="onCanvasBackground">
        <div ref="content" class="editor-content" :style="{ width: `${size.width}px`, height: `${size.height}px` }">
          <svg class="editor-edges" :width="size.width" :height="size.height">
            <path
              v-for="entry in edges"
              :key="entry.edge.id"
              class="editor-edge"
              :class="{ selected: selectedEdge === entry.edge.id, bad: issueSet.has(`edge:${entry.edge.id}`) }"
              :d="edgePath(entry.points.from, entry.points.to)"
              @click.stop="selectEdge(entry.edge.id)"
            />
            <path
              v-if="pending"
              class="editor-edge pending"
              :d="`M ${pending.startX} ${pending.startY} L ${pending.x} ${pending.y}`"
            />
          </svg>

          <div
            v-for="node in definition.nodes"
            :key="node.id"
            :data-node-card="node.id"
            class="editor-node"
            :class="{ run: node.kind === 'run', form: node.kind === 'form', selected: selected === node.id }"
            :style="{ left: `${node.position.x}px`, top: `${node.position.y}px`, width: `${NODE_WIDTH}px` }"
            @pointerdown="startDrag($event, node)"
          >
            <div class="editor-node-head" :style="{ height: `${HEADER_HEIGHT}px` }">
              <span class="editor-node-kind">{{ node.kind === 'run' ? 'run' : 'form' }}</span>
              <span class="editor-node-title">{{ node.title || node.id }}</span>
            </div>
            <div
              v-for="row in rowsFor(node)"
              :key="`${row.kind}:${row.id}`"
              class="editor-node-row"
              :style="{ height: `${ROW_HEIGHT}px` }"
              :data-port-kind="row.kind === 'input' ? 'input' : row.kind"
              :data-port-id="row.id"
              :data-node-id="node.id"
              @pointerdown="row.kind !== 'input' && startConnect($event, node, row)"
            >
              <span v-if="row.kind === 'input'" class="port in" title="Drop a connection here"></span>
              <span class="editor-row-label">{{ row.label }}</span>
              <span v-if="row.kind !== 'input'" class="port out" title="Drag to a target input"></span>
            </div>
          </div>
        </div>
      </div>

      <aside v-if="selectedNode" class="editor-inspector">
        <div class="row" style="justify-content: space-between">
          <h3 style="margin: 0">{{ selectedNode.kind === 'run' ? 'Run step' : 'Form step' }}</h3>
          <button class="btn sm ghost" @click="deleteSelected">Delete</button>
        </div>
        <div class="field">
          <label :for="`node-title`">Title</label>
          <input id="node-title" v-model="selectedNode.title" class="input" />
        </div>

        <template v-if="selectedNode.kind === 'run'">
          <div class="field">
            <label for="node-harness">Harness</label>
            <select id="node-harness" v-model="selectedNode.harnessId" class="input">
              <option value="">Default harness</option>
              <option v-for="harness in harnesses" :key="harness.id" :value="harness.id">
                {{ harness.name }}
              </option>
            </select>
          </div>
          <div class="field">
            <label for="node-model">Model override (optional)</label>
            <input id="node-model" v-model="selectedNode.model" class="input" placeholder="provider/model" />
          </div>
          <div class="field">
            <label for="node-cwd">Working directory (optional)</label>
            <input id="node-cwd" v-model="selectedNode.cwd" class="input" placeholder="Defaults to the run's task" />
          </div>
          <div class="field">
            <label for="node-prompt">Prompt</label>
            <textarea id="node-prompt" v-model="selectedNode.promptTemplate" class="textarea" rows="6"></textarea>
            <p class="faint" style="margin: 4px 0 0">
              Reference an input as <code v-pre>{{ name }}</code
              >, one value as <code v-pre>{{ name[0] }}</code
              >, or a joined list as <code v-pre>{{ name.join(', ') }}</code
              >.
            </p>
          </div>

          <div class="field">
            <span>Inputs</span>
            <div v-for="input in selectedNode.inputs" :key="input.id" class="row" style="gap: 6px; margin-top: 6px">
              <input v-model="input.name" class="input" placeholder="name" :aria-label="`Input name`" />
              <button class="btn sm ghost" @click="removeNodeInput(selectedNode, input.id)">×</button>
            </div>
            <button class="btn sm" style="margin-top: 6px" @click="addInput(selectedNode)">+ Input</button>
          </div>
        </template>

        <template v-else>
          <div v-for="(field, index) in selectedNode.fields" :key="field.id" class="editor-field-group">
            <div class="row" style="justify-content: space-between">
              <strong>Field {{ index + 1 }}</strong>
              <button class="btn sm ghost" @click="removeNodeField(selectedNode, field.id)">×</button>
            </div>
            <div class="field">
              <label :for="`field-title-${field.id}`">Title</label>
              <input :id="`field-title-${field.id}`" v-model="field.title" class="input" />
            </div>
            <div class="field">
              <label :for="`field-type-${field.id}`">Type</label>
              <select :id="`field-type-${field.id}`" v-model="field.type" class="input">
                <option v-for="type in FIELD_TYPES" :key="type" :value="type">{{ type }}</option>
              </select>
            </div>
            <label class="row" style="gap: 6px; align-items: center">
              <input v-model="field.required" type="checkbox" />
              <span>Required</span>
            </label>
            <div class="field">
              <label :for="`field-default-${field.id}`">Default value</label>
              <input :id="`field-default-${field.id}`" v-model="field.defaultValue" class="input" />
            </div>
            <div v-if="field.type === 'select'" class="field">
              <span>Options (one per line)</span>
              <textarea
                :value="(field.options || []).join('\n')"
                class="textarea"
                rows="3"
                @input="field.options = $event.target.value.split('\n')"
              ></textarea>
            </div>
            <div v-if="field.type === 'slider' || field.type === 'number'" class="row" style="gap: 6px">
              <input v-model.number="field.min" class="input" type="number" placeholder="min" />
              <input v-model.number="field.max" class="input" type="number" placeholder="max" />
              <input v-model.number="field.step" class="input" type="number" placeholder="step" />
            </div>
          </div>
          <button class="btn sm" @click="addField(selectedNode)">+ Field</button>
        </template>
      </aside>
      <aside v-else class="editor-inspector faint">
        Select a node to edit it. Connections run from an answer or a field value into a named input, and a form appears
        only when its downstream step is ready.
      </aside>
    </div>
  </div>
</template>

<style scoped>
.editor-panel {
  display: flex;
  flex-direction: column;
}
.editor-hint,
.editor-issues {
  margin: 0 0 10px;
  font-size: 13px;
}
.editor-issues {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: var(--warn);
}
.editor-body {
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-height: 420px;
}
.editor-canvas {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  max-height: 65vh;
  position: relative;
}
.editor-content {
  position: relative;
}
.editor-edges {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.editor-edge {
  fill: none;
  stroke: var(--faint);
  stroke-width: 1.6;
  pointer-events: stroke;
  cursor: pointer;
}
.editor-edge.selected {
  stroke: var(--danger);
}
.editor-edge.pending {
  stroke: var(--accent);
  stroke-dasharray: 4 4;
}
.editor-node {
  position: absolute;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  touch-action: none;
  user-select: none;
  cursor: grab;
}
.editor-node.selected {
  border-color: var(--accent);
}
.editor-node.form {
  background: var(--bg-1);
}
.editor-node-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border);
}
.editor-node-kind {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 6px;
}
.editor-node-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.editor-node-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
}
.editor-node-row:last-child {
  border-bottom: none;
  border-radius: 0 0 var(--radius) var(--radius);
}
.editor-row-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.port {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--muted);
  background: var(--bg-2);
  flex-shrink: 0;
}
.port.in {
  margin-right: 6px;
}
.port.out {
  margin-left: 6px;
  cursor: crosshair;
}
.editor-node-row:hover .port.out {
  border-color: var(--accent);
}
.editor-inspector {
  width: 300px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  overflow-y: auto;
  max-height: 65vh;
  font-size: 13px;
}
.editor-field-group {
  border-top: 1px solid var(--border);
  margin-top: 10px;
  padding-top: 8px;
}
@media (max-width: 760px) {
  .editor-body {
    flex-direction: column;
  }
  .editor-canvas {
    max-height: 50vh;
  }
  .editor-inspector {
    width: auto;
    max-height: none;
  }
}
</style>
