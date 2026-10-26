<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { checkLabel, checkTone, checksSummary, ciLabel, ciTone, sortChecks } from '../myPulls'

// The CI badge on a My PRs row, opening the pull request's individual checks the
// way GitHub's checks popover does. The page load carries only the rollup state,
// so the checks are read when the popover opens and kept for the visit.
//
// The panel is fixed-positioned from the badge's rectangle: the table scrolls
// sideways in a wrapper, which would clip a panel positioned inside the cell.
const props = defineProps({
  pull: { type: Object, required: true }
})

// The panel is kept inside the viewport, and opened upward when the badge sits
// too low for it to fit below.
const PANEL_WIDTH = 380
const PANEL_MARGIN = 12
const MIN_PANEL_HEIGHT = 180
const SPACE_FOR_ABOVE = 260

const open = ref(false)
const loading = ref(false)
const error = ref('')
const checks = ref([])
const total = ref(0)
const loaded = ref(false)
const trigger = ref(null)
const panel = ref(null)
const panelStyle = ref({})

const tone = computed(() => ciTone(props.pull))
const label = computed(() => ciLabel(props.pull))
const summary = computed(() => checksSummary(checks.value))
const trimmed = computed(() => total.value > checks.value.length)

// Put the panel under the badge, or over it near the bottom of the window, and
// cap its height to the room on that side.
function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const width = Math.min(PANEL_WIDTH, window.innerWidth - PANEL_MARGIN * 2)
  const left = Math.max(PANEL_MARGIN, Math.min(rect.left, window.innerWidth - width - PANEL_MARGIN))
  const spaceBelow = window.innerHeight - rect.bottom
  const openAbove = spaceBelow < SPACE_FOR_ABOVE && rect.top > spaceBelow
  const maxHeight = Math.max(MIN_PANEL_HEIGHT, (openAbove ? rect.top : spaceBelow) - PANEL_MARGIN)
  panelStyle.value = openAbove
    ? {
        left: `${left}px`,
        bottom: `${window.innerHeight - rect.top + 6}px`,
        width: `${width}px`,
        maxHeight: `${maxHeight}px`
      }
    : {
        left: `${left}px`,
        top: `${rect.bottom + 6}px`,
        width: `${width}px`,
        maxHeight: `${maxHeight}px`
      }
}

async function load(force = false) {
  if (loaded.value && !force) return
  loading.value = true
  error.value = ''
  try {
    const report = await api.myPulls.checks({
      repository: props.pull.repository,
      number: props.pull.number,
      refresh: force
    })
    checks.value = sortChecks(report.checks || [])
    total.value = Number(report.total) || checks.value.length
    error.value = report.error || ''
    loaded.value = !report.error
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function toggle() {
  if (open.value) {
    open.value = false
    return
  }
  open.value = true
  await nextTick()
  place()
  await load()
}

function close() {
  open.value = false
}

function onDocumentClick(event) {
  if (!open.value) return
  if (panel.value?.contains(event.target) || trigger.value?.contains(event.target)) return
  close()
}

function onKeydown(event) {
  if (event.key !== 'Escape' || !open.value) return
  close()
  trigger.value?.focus()
}

function onViewportChange() {
  if (open.value) place()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onViewportChange)
  window.addEventListener('scroll', onViewportChange, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
})
</script>

<template>
  <span class="my-pulls-ci">
    <button
      ref="trigger"
      type="button"
      class="badge my-pulls-ci-button"
      :class="tone"
      aria-haspopup="dialog"
      :aria-expanded="open ? 'true' : 'false'"
      :title="`Show the checks for ${pull.repository}#${pull.number}`"
      @click="toggle"
    >
      {{ label }}
      <span class="my-pulls-ci-caret" aria-hidden="true"></span>
    </button>
    <div
      v-if="open"
      ref="panel"
      class="my-pulls-checks"
      role="dialog"
      :aria-label="`Checks for ${pull.repository}#${pull.number}`"
      :style="panelStyle"
    >
      <div class="my-pulls-checks-head">
        <span class="my-pulls-checks-title">Checks</span>
        <a v-if="pull.url" class="my-pulls-checks-all" :href="`${pull.url}/checks`" target="_blank" rel="noopener"
          >View on GitHub</a
        >
      </div>
      <p v-if="summary && !loading && !error" class="faint my-pulls-checks-summary">{{ summary }}</p>
      <div v-if="loading" class="my-pulls-checks-status">
        <span class="spinner" aria-hidden="true"></span>
      </div>
      <template v-else-if="error">
        <p class="my-pulls-checks-error">{{ error }}</p>
        <button class="btn sm ghost" type="button" @click="load(true)">Retry</button>
      </template>
      <ul v-else-if="checks.length" class="my-pulls-checks-list">
        <li
          v-for="check in checks"
          :key="`${check.name}-${check.url}`"
          class="my-pulls-check"
          :class="`is-${check.state}`"
        >
          <span class="my-pulls-check-dot" :class="checkTone(check)" aria-hidden="true"></span>
          <a
            v-if="check.url"
            class="my-pulls-check-name"
            :href="check.url"
            target="_blank"
            rel="noopener"
            :title="check.description || check.name"
            >{{ check.name }}</a
          >
          <span v-else class="my-pulls-check-name" :title="check.description || check.name">{{ check.name }}</span>
          <span class="my-pulls-check-state" :class="checkTone(check)">{{ checkLabel(check) }}</span>
        </li>
      </ul>
      <p v-else class="faint my-pulls-checks-empty">No checks reported for this pull request.</p>
      <p v-if="!loading && !error && trimmed" class="faint my-pulls-checks-more">
        Showing {{ checks.length }} of {{ total }} checks.
      </p>
    </div>
  </span>
</template>
