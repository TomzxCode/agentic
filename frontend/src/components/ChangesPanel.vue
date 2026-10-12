<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])

const classOptions = ['feature', 'bugfix', 'refactor', 'chore', 'docs', 'test', 'trivial'].map((value) => ({
  value,
  label: value
}))
const kindOptions = ['question', 'correction', 'manual_fix', 'rerun', 'approval', 'other'].map((value) => ({
  value,
  label: value.replace('_', ' ')
}))

const draft = reactive({ title: '', change_class: 'feature', external_ref: '' })
const busy = ref(false)
// The change whose intervention is being captured; only that row shows the kind picker.
const interveningId = ref('')
const interventionKind = ref('')

const changes = computed(() => props.task.changes || [])

const STATUS_BADGE = {
  proposed: 'badge',
  verified: 'badge run',
  accepted: 'badge ok',
  rejected: 'badge danger',
  reverted: 'badge warn'
}

watch(
  () => props.task.id,
  () => (interveningId.value = '')
)

async function create() {
  if (!draft.title.trim()) return
  busy.value = true
  try {
    await api.changes.create({
      task_id: props.task.id,
      title: draft.title,
      change_class: draft.change_class,
      external_ref: draft.external_ref || null
    })
    draft.title = ''
    draft.external_ref = ''
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function transition(change, status) {
  try {
    await api.changes.transition(change.id, status)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

function startIntervene(change) {
  interveningId.value = change.id
  interventionKind.value = ''
}

function cancelIntervene() {
  interveningId.value = ''
}

async function saveIntervene(change) {
  if (!interventionKind.value) return
  try {
    await api.changes.intervene(change.id, { kind: interventionKind.value })
    interveningId.value = ''
    emit('changed')
    store.notify(`Intervention recorded (${interventionKind.value})`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function remove(change) {
  if (!confirm(`Delete change "${change.title || change.id}"?`)) return
  try {
    await api.changes.remove(change.id)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>
        Changes <span class="faint">{{ changes.length }}</span>
      </h2>
    </div>

    <div v-if="!changes.length" class="faint" style="margin-bottom: 12px">
      No changes yet. Record one for each unit of work the metrics should count.
    </div>

    <div v-for="change in changes" :key="change.id" class="change-row">
      <span class="grow">
        <span :class="STATUS_BADGE[change.status] || 'badge'">{{ change.status }}</span>
        <span class="faint">{{ change.change_class }}</span>
        {{ change.title || change.id }}
        <span v-if="change.human_intervened" class="badge warn" title="A human touched this change"
          >touched {{ change.intervention_count }}</span
        >
        <span v-if="change.external_ref" class="faint">· {{ change.external_ref }}</span>
        <span class="faint">· {{ timeAgo(change.opened_at) }}</span>
      </span>

      <div v-if="interveningId === change.id" class="row intervene-kind">
        <SearchSelect v-model="interventionKind" :options="kindOptions" :sort="false" placeholder="Intervention kind" />
        <button class="btn sm primary" :disabled="!interventionKind" @click="saveIntervene(change)">Save</button>
        <button class="btn sm ghost" @click="cancelIntervene">Cancel</button>
      </div>
      <div v-else class="row">
        <button v-if="change.status === 'proposed'" class="btn sm" @click="transition(change, 'verified')">
          Verify
        </button>
        <button
          v-if="['proposed', 'verified'].includes(change.status)"
          class="btn sm primary"
          @click="transition(change, 'accepted')"
        >
          Accept
        </button>
        <button
          v-if="['proposed', 'verified'].includes(change.status)"
          class="btn sm ghost"
          @click="transition(change, 'rejected')"
        >
          Reject
        </button>
        <button v-if="change.status === 'accepted'" class="btn sm danger" @click="transition(change, 'reverted')">
          Revert
        </button>
        <button class="btn sm ghost" @click="startIntervene(change)">Intervene</button>
        <button class="btn sm ghost" title="Delete" @click="remove(change)">Delete</button>
      </div>
    </div>

    <div class="row metric-form" style="margin-top: 12px">
      <input v-model="draft.title" class="input grow" placeholder="What changed?" @keyup.enter="create" />
      <input v-model="draft.external_ref" class="input" placeholder="PR / ref (optional)" />
      <SearchSelect v-model="draft.change_class" :options="classOptions" :sort="false" placeholder="Class" />
      <button class="btn primary" :disabled="busy || !draft.title.trim()" @click="create">
        <span v-if="busy" class="spinner"></span> Record change
      </button>
    </div>
  </section>
</template>
