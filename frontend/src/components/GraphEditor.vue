<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NODE_WIDTH,
  HEADER_HEIGHT,
  ROW_HEIGHT,
  FIELD_TYPES,
  autoLayout,
  blankCliNode,
  blankField,
  blankFormNode,
  blankInput,
  blankRunNode,
  canvasSize,
  canConnect,
  connect,
  dropDanglingEdges,
  edgeEndpoints,
  edgePath,
  editorIssues,
  nearestPort,
  nodeRows,
  normalizeDefinition,
  portPoint,
  relayout,
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
// A connection waiting for its target: tap a source row, then tap an input or
// a form field. This is the phone-friendly path, since it needs no held drag
// and survives scrolling to a node that is off screen.
const armed = ref(null)
// The node being dragged, with the grab offset inside the card.
const dragging = ref(null)
const issues = ref([])
const saving = ref(false)
const content = ref(null)
// A source row pressed but not yet moved: it arms on release, so a tap and a
// drag start the same way and only the distance tells them apart.
const rowPress = ref(null)

// Whether the canvas arranges itself as the graph changes: never, when a step
// is added, when one is removed, or both. A per-device view preference, kept
// in localStorage like the sidebar's, not a server setting.
const LAYOUT_KEY = 'agentic.executionGraph.autoLayout'
const LAYOUT_MODES = ['off', 'add', 'remove', 'always']
const storedLayout = localStorage.getItem(LAYOUT_KEY)
const autoLayoutMode = ref(LAYOUT_MODES.includes(storedLayout) ? storedLayout : 'off')
watch(autoLayoutMode, (mode) => localStorage.setItem(LAYOUT_KEY, mode))

const size = computed(() => canvasSize(definition.value))
const issueSet = computed(() => new Set(issues.value))
const selectedNode = computed(() => definition.value.nodes.find((node) => node.id === selected.value) || null)
// While a source is armed, every row a tap could land on is marked, so the
// eligible targets are obvious without hovering (phones have no hover).
const eligibleRows = computed(() => {
  const allowed = new Set()
  if (!armed.value) return allowed
  for (const node of definition.value.nodes) {
    for (const row of nodeRows(node)) {
      if (!canConnect(definition.value, armed.value.sourceId, armed.value.sourceFieldId, node.id, row)) continue
      allowed.add(rowKey(node, row))
    }
  }
  return allowed
})

const edges = computed(() =>
  definition.value.edges
    .map((edge) => ({ edge, points: edgeEndpoints(definition.value, edge) }))
    .filter((entry) => entry.points)
)

// A selected connection, named by its two ends, so the remove action can say
// what it will disconnect and a phone never needs the Delete key.
const selectedEdgeInfo = computed(() => {
  const edge = definition.value.edges.find((candidate) => candidate.id === selectedEdge.value)
  if (!edge) return null
  const source = nodeById(edge.source)
  const target = nodeById(edge.target)
  if (!source || !target) return null
  const sourceRow =
    source.kind === 'form'
      ? nodeRows(source).find((row) => row.kind === 'field' && row.id === edge.sourceFieldId)
      : nodeRows(source).find((row) => row.kind === 'output')
  const targetRow =
    target.kind === 'form'
      ? nodeRows(target).find((row) => row.kind === 'field' && row.id === edge.targetFieldId)
      : nodeRows(target).find((row) => row.kind === 'input' && row.id === edge.targetInputId)
  return {
    edge,
    source: `${source.title || source.id} · ${sourceRow?.label || '?'}`,
    target: `${target.title || target.id} · ${targetRow?.label || '?'}`
  }
})

function nodeById(id) {
  return definition.value.nodes.find((node) => node.id === id)
}

function rowKey(node, row) {
  return `${node.id}:${row.kind}:${row.id}`
}

// Arm a source row as the start of a connection. The target is a second tap,
// so the finger never has to hold the source while finding its target.
function arm(node, row) {
  if (row.kind === 'input') return
  selectedEdge.value = ''
  armed.value = {
    sourceId: node.id,
    sourceFieldId: row.kind === 'field' ? row.id : '',
    label: row.label,
    nodeTitle: node.title || node.id
  }
}

function cancelConnect() {
  armed.value = null
}

function isArmedSource(node, row) {
  if (!armed.value || armed.value.sourceId !== node.id) return false
  return row.kind === 'field' ? row.id === armed.value.sourceFieldId : row.kind === 'output'
}

// A tap while armed lands on a row: connect when it can take the link, cancel
// when it is the armed node itself, and otherwise leave the connection open.
function connectArmed(node, row) {
  const source = armed.value
  if (!source) return
  if (node.id === source.sourceId) {
    cancelConnect()
    return
  }
  if (!eligibleRows.value.has(rowKey(node, row))) return
  applyConnection(source.sourceId, source.sourceFieldId, node.id, row)
  cancelConnect()
}

// Add an edge, then re-arrange when the chosen mode covers adds: a new link
// can move a node into a deeper dependency layer. Refused and duplicate
// connections leave the canvas alone.
function applyConnection(sourceId, sourceFieldId, targetId, port) {
  const next = connect(definition.value, sourceId, sourceFieldId, targetId, port)
  if (next === definition.value) return false
  definition.value = laysOut('add') ? relayout(next) : next
  return true
}

function addNode(kind) {
  const node = kind === 'form' ? blankFormNode() : kind === 'cli' ? blankCliNode() : blankRunNode()
  // Drop new nodes where the canvas is scrolled to, stepping each one down so
  // consecutive additions do not stack on top of each other.
  const box = content.value?.parentElement
  const step = definition.value.nodes.length * 28
  node.position = { x: (box?.scrollLeft || 0) + 60 + step, y: (box?.scrollTop || 0) + 60 + step }
  definition.value.nodes.push(node)
  selected.value = node.id
  selectedEdge.value = ''
  if (laysOut('add')) definition.value = relayout(definition.value)
}

// True when the chosen auto-layout mode covers this kind of change.
function laysOut(change) {
  return autoLayoutMode.value === 'always' || autoLayoutMode.value === change
}

// Arranges every card by dependency layer, discarding hand-placed positions,
// and scrolls back to the corner the layout starts at so the result is visible.
function arrange() {
  definition.value = relayout(definition.value)
  content.value?.parentElement?.scrollTo?.({ top: 0, left: 0 })
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
    definition.value = {
      ...definition.value,
      edges: definition.value.edges.filter((edge) => edge.id !== selectedEdge.value)
    }
    selectedEdge.value = ''
    if (laysOut('remove')) definition.value = relayout(definition.value)
    return
  }
  if (!selected.value) return
  definition.value = dropDanglingEdges(removeNode(definition.value, selected.value))
  selected.value = ''
  if (laysOut('remove')) definition.value = relayout(definition.value)
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

// A press on the card body: on a phone the body pans the canvas and a tap
// selects, while dragging a card is left to its header handle. A mouse keeps
// the old drag-anywhere behaviour.
function onNodePointerDown(event, node) {
  if (armed.value) {
    // Taps that land on a row were handled there; the rest of the card keeps
    // the armed connection instead of starting a drag or a selection.
    event.stopPropagation()
    return
  }
  if (event.pointerType === 'touch') {
    selectNode(node.id)
    return
  }
  startDrag(event, node)
}

function onRowPointerDown(event, node, row) {
  if (armed.value) {
    event.stopPropagation()
    connectArmed(node, row)
    return
  }
  if (row.kind === 'input') return
  event.stopPropagation()
  // A mouse draws the connection immediately; a finger arms the row on
  // release, so a swipe can still pan the canvas instead.
  rowPress.value = {
    nodeId: node.id,
    row,
    startX: event.clientX,
    startY: event.clientY,
    moved: false
  }
  if (event.pointerType !== 'touch') startConnect(event, node, row)
}

function onPointerMove(event) {
  if (rowPress.value && !rowPress.value.moved) {
    const dx = event.clientX - rowPress.value.startX
    const dy = event.clientY - rowPress.value.startY
    if (Math.hypot(dx, dy) > 8) rowPress.value.moved = true
  }
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
  const press = rowPress.value
  rowPress.value = null
  if (dragging.value) {
    dragging.value = null
    return
  }
  // A press that never moved is a tap: arm the source instead of resolving a
  // drop that went nowhere.
  if (press && !press.moved) {
    pending.value = null
    const node = nodeById(press.nodeId)
    if (node) arm(node, press.row)
    return
  }
  if (!pending.value) return
  // Land on whatever port is under the pointer, if any.
  const landing = document.elementFromPoint(event.clientX, event.clientY)
  const drop = landing?.closest('[data-port-kind][data-node-id]')
  if (drop) {
    const port = { kind: drop.dataset.portKind, id: drop.dataset.portId }
    applyConnection(pending.value.sourceId, pending.value.sourceFieldId, drop.dataset.nodeId, port)
  } else {
    // A finger that missed the row by a few pixels still lands on the port it
    // was aiming at.
    const nearest = nearestPort(
      definition.value,
      pending.value.sourceId,
      pending.value.sourceFieldId,
      { x: pending.value.x, y: pending.value.y },
      48
    )
    if (nearest) {
      applyConnection(pending.value.sourceId, pending.value.sourceFieldId, nearest.nodeId, {
        kind: nearest.kind,
        id: nearest.id
      })
    }
  }
  pending.value = null
}

function onPointerCancel() {
  dragging.value = null
  pending.value = null
  rowPress.value = null
}

function startConnect(event, node, row) {
  event.stopPropagation()
  selectedEdge.value = ''
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
  armed.value = null
  selected.value = ''
  selectedEdge.value = ''
}

function onKeyDown(event) {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
  if ((event.key === 'Delete' || event.key === 'Backspace') && !typing && (selected.value || selectedEdge.value)) {
    event.preventDefault()
    deleteSelected()
  }
  if (event.key === 'Escape') {
    armed.value = null
    pending.value = null
  }
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
  window.addEventListener('pointercancel', onPointerCancel)
  window.addEventListener('keydown', onKeyDown)
})
onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
  window.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <div class="panel editor-panel">
    <div class="panel-head">
      <h2>{{ graph.name }}</h2>
      <span class="row" style="gap: 6px; flex-wrap: wrap">
        <button class="btn sm" @click="addNode('run')">+ Run step</button>
        <button class="btn sm" @click="addNode('cli')">+ Command step</button>
        <button class="btn sm" @click="addNode('form')">+ Form step</button>
        <label class="editor-layout-mode" title="Keep the graph arranged as steps and connections are added or removed">
          <span>Auto-layout</span>
          <select v-model="autoLayoutMode" class="input" aria-label="When to auto-layout the graph">
            <option value="off">never</option>
            <option value="add">on add</option>
            <option value="remove">on remove</option>
            <option value="always">always</option>
          </select>
        </label>
        <button class="btn sm" title="Arrange every step automatically" @click="arrange">Arrange</button>
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
      Tap a step's output row, then tap the input or form field it should feed (on a computer you can also drag from a
      right-side dot). Tap a connection line to select it, then press Remove. Drag a card by its header to move it.
      Select something and press Delete to remove it.
    </p>

    <div v-if="armed" class="editor-armed" role="status">
      <span>
        Connecting <strong>{{ armed.label }}</strong> from <strong>{{ armed.nodeTitle }}</strong
        >. Tap an input or a form field, or tap the source again to cancel.
      </span>
      <button class="btn sm" @click="cancelConnect">Cancel</button>
    </div>

    <div v-else-if="selectedEdgeInfo" class="editor-armed" role="status">
      <span>
        Connection <strong>{{ selectedEdgeInfo.source }}</strong> → <strong>{{ selectedEdgeInfo.target }}</strong
        >.
      </span>
      <button class="btn sm danger" @click="deleteSelected">Remove</button>
    </div>

    <div class="editor-body">
      <div class="editor-canvas" @pointerdown="onCanvasBackground">
        <div ref="content" class="editor-content" :style="{ width: `${size.width}px`, height: `${size.height}px` }">
          <svg class="editor-edges" :width="size.width" :height="size.height">
            <template v-for="entry in edges" :key="entry.edge.id">
              <path
                class="editor-edge"
                :class="{ selected: selectedEdge === entry.edge.id, bad: issueSet.has(`edge:${entry.edge.id}`) }"
                :d="edgePath(entry.points.from, entry.points.to)"
                @click.stop="selectEdge(entry.edge.id)"
              />
              <!-- A wide transparent band over the same curve, so a finger
                   does not have to hit a 1.6 px stroke to select it. -->
              <path
                class="editor-edge-hit"
                :d="edgePath(entry.points.from, entry.points.to)"
                @click.stop="selectEdge(entry.edge.id)"
              />
            </template>
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
            @pointerdown="onNodePointerDown($event, node)"
          >
            <div
              class="editor-node-head"
              :style="{ height: `${HEADER_HEIGHT}px` }"
              title="Drag to move"
              @pointerdown.stop="startDrag($event, node)"
            >
              <span class="editor-node-kind">{{ node.kind }}</span>
              <span class="editor-node-title">{{ node.title || node.id }}</span>
              <span class="editor-node-grip" aria-hidden="true">⠿</span>
            </div>
            <div
              v-for="row in rowsFor(node)"
              :key="`${row.kind}:${row.id}`"
              class="editor-node-row"
              :class="{
                eligible: eligibleRows.has(rowKey(node, row)),
                source: isArmedSource(node, row)
              }"
              :style="{ height: `${ROW_HEIGHT}px` }"
              :data-port-kind="row.kind === 'input' ? 'input' : row.kind"
              :data-port-id="row.id"
              :data-node-id="node.id"
              @pointerdown="onRowPointerDown($event, node, row)"
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
          <h3 style="margin: 0">
            {{ selectedNode.kind === 'run' ? 'Run step' : selectedNode.kind === 'cli' ? 'Command step' : 'Form step' }}
          </h3>
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
        </template>

        <template v-if="selectedNode.kind !== 'form'">
          <div class="field">
            <label for="node-cwd">Working directory (optional)</label>
            <input
              id="node-cwd"
              v-model="selectedNode.cwd"
              class="input"
              :placeholder="
                selectedNode.kind === 'cli' ? 'Defaults to the server\'s own directory' : 'Defaults to the run\'s task'
              "
            />
          </div>
          <div v-if="selectedNode.kind === 'run'" class="field">
            <label for="node-prompt">Prompt</label>
            <textarea id="node-prompt" v-model="selectedNode.promptTemplate" class="textarea" rows="6"></textarea>
            <p class="faint" style="margin: 4px 0 0">
              Reference an input as <code v-pre>{{ name }}</code
              >, one value as <code v-pre>{{ name[0] }}</code
              >, or a joined list as <code v-pre>{{ name.join(', ') }}</code
              >.
            </p>
          </div>
          <div v-else class="field">
            <label for="node-command">Command (after `agentic`)</label>
            <textarea
              id="node-command"
              v-model="selectedNode.command"
              class="textarea"
              rows="4"
              :style="{ fontFamily: 'var(--mono)' }"
              placeholder='task create --title "Fix {{ name }}"'
            ></textarea>
            <p class="faint" style="margin: 4px 0 0">
              Runs <code>agentic --format json</code> plus this command line against this server; its stdout feeds
              downstream inputs. Reference an input as <code v-pre>{{ name }}</code
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
        <template v-if="selectedEdgeInfo">
          Connection <strong>{{ selectedEdgeInfo.source }}</strong> → <strong>{{ selectedEdgeInfo.target }}</strong
          >. Use Remove above to disconnect it.
        </template>
        <template v-else>
          Select a node to edit it. Connections run from an answer or a field value into a named input, and a form
          appears only when its downstream step is ready.
        </template>
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
/* The "Auto-layout" select beside the toolbar buttons: a compact labeled
   control that sits on the same line as them. */
.editor-layout-mode {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}
.editor-layout-mode select {
  width: auto;
  padding: 4px 6px;
  font-size: 12px;
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
/* The selectable band around a connection: invisible, but 24 px wide, so a
   tap on a phone hits the curve instead of the canvas behind it. */
.editor-edge-hit {
  fill: none;
  stroke: transparent;
  stroke-width: 24;
  pointer-events: stroke;
  cursor: pointer;
}
.editor-edge.pending {
  stroke: var(--accent);
  stroke-dasharray: 4 4;
}
.editor-armed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 0 10px;
  padding: 8px 10px;
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  background: var(--bg-1);
  font-size: 13px;
}
.editor-node {
  position: absolute;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  /* A swipe over the card body pans the canvas; only the header and the ports
     opt out, so a phone can still move around a dense canvas. */
  touch-action: pan-x pan-y;
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
  /* The header is the card's drag handle, so it keeps the gesture from
     turning into a canvas pan. */
  touch-action: none;
  cursor: grab;
}
.editor-node-grip {
  margin-left: auto;
  color: var(--muted);
  font-size: 13px;
  line-height: 1;
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
  padding: 0 10px;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
}
/* While a connection is armed, every row a tap could land on is marked, so a
   phone user sees the targets without hovering over them. */
.editor-node-row.eligible {
  background: rgba(110, 231, 183, 0.12);
  box-shadow: inset 2px 0 0 var(--accent);
}
.editor-node-row.eligible .port {
  border-color: var(--accent);
}
.editor-node-row.source {
  background: rgba(110, 231, 183, 0.22);
}
.editor-node-row.source .port {
  background: var(--accent);
  border-color: var(--accent);
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
  /* Push the output dot to the row's right edge; the label stays beside the
     left edge, where the incoming dot sits on an input row. */
  margin-left: auto;
  cursor: crosshair;
}
.port.out,
.port.in {
  touch-action: none;
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
  /* Match the toolbar buttons' phone sizing, and keep iOS from zooming on the
     select when it takes focus. */
  .editor-layout-mode select {
    min-height: 36px;
    padding: 7px 11px;
    font-size: 16px;
  }
}
</style>
