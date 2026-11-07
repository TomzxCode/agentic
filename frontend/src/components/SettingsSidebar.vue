<script setup>
import { computed, onUnmounted, ref } from 'vue'
import Icon from './Icon.vue'
import {
  moveNavItem,
  moveNavItemTo,
  resetSidebarNav,
  setNavHidden,
  sidebarNavCustomized,
  sidebarNavList
} from '../sidebarNav'
import { setSidebarLayout, sidebarLayout } from '../sidebarLayout'

// The "Sidebar" settings section: the sidebar's shape (full or icon rail), and
// which page icons the bottom nav shows, and their order. A per-device choice in
// localStorage (owned by sidebarLayout.js and sidebarNav.js), so there is no
// server round trip and no save button.
//
// Rows are reordered by dragging the grip. Pointer events (not the HTML5 drag
// API, which touch browsers do not fire) so a drag works on a phone too, and
// the grip also answers to the arrow keys so the order is editable from the
// keyboard.

const LAYOUTS = [
  { id: 'full', label: 'Full', hint: 'The task list above the page icons.' },
  {
    id: 'rail',
    label: 'Icon rail',
    hint: 'A thin column of page icons over the full height (a narrow drawer on a phone).'
  }
]

const layoutHint = computed(() => LAYOUTS.find((option) => option.id === sidebarLayout.value).hint)

const listEl = ref(null)
const draggingId = ref(null)
let drag = null

function onGripDown(event, item, index) {
  if (event.button > 0) return
  drag = { id: item.id, index }
  draggingId.value = item.id
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
  window.addEventListener('pointercancel', onDragEnd)
  event.preventDefault()
}

// Live-reorder as the pointer passes each row's midpoint, reading the rows'
// current positions (they shift as the list reorders under the drag).
function onDragMove(event) {
  if (!drag) return
  const rows = Array.from(listEl.value?.querySelectorAll('.nav-config-row') || [])
  const y = event.clientY
  let target = rows.length - 1
  for (let i = 0; i < rows.length; i += 1) {
    const rect = rows[i].getBoundingClientRect()
    if (y < rect.top + rect.height / 2) {
      target = i
      break
    }
  }
  if (target !== drag.index) {
    moveNavItemTo(drag.id, target)
    drag.index = target
  }
}

function onDragEnd() {
  if (!drag) return
  drag = null
  draggingId.value = null
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointercancel', onDragEnd)
}

function onGripKeydown(event, id) {
  if (event.key === 'ArrowUp') {
    moveNavItem(id, -1)
    event.preventDefault()
  } else if (event.key === 'ArrowDown') {
    moveNavItem(id, 1)
    event.preventDefault()
  }
}

onUnmounted(onDragEnd)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Sidebar</h2>
      <button v-if="sidebarNavCustomized" class="btn sm" @click="resetSidebarNav">Reset to default</button>
    </div>

    <div class="field">
      <label>Layout</label>
      <div class="row" role="radiogroup" aria-label="Sidebar layout">
        <button
          v-for="option in LAYOUTS"
          :key="option.id"
          type="button"
          class="btn sm sidebar-layout-option"
          :class="{ primary: sidebarLayout === option.id }"
          role="radio"
          :aria-checked="sidebarLayout === option.id"
          @click="setSidebarLayout(option.id)"
        >
          {{ option.label }}
        </button>
      </div>
      <p class="faint" style="margin: 6px 0 0">{{ layoutHint }}</p>
    </div>

    <p class="faint" style="margin-top: 0">
      Choose which page icons appear in the sidebar, and drag the grip to reorder them. Saved on this device.
    </p>

    <ul ref="listEl" class="nav-config">
      <li
        v-for="(item, index) in sidebarNavList"
        :key="item.id"
        class="nav-config-row"
        :class="{ 'is-hidden': item.hidden, dragging: draggingId === item.id }"
      >
        <button
          class="nav-config-grip"
          type="button"
          :aria-label="`Reorder ${item.label}`"
          title="Drag to reorder"
          @pointerdown="onGripDown($event, item, index)"
          @keydown="onGripKeydown($event, item.id)"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="currentColor">
            <circle cx="9" cy="6" r="1.5" />
            <circle cx="15" cy="6" r="1.5" />
            <circle cx="9" cy="12" r="1.5" />
            <circle cx="15" cy="12" r="1.5" />
            <circle cx="9" cy="18" r="1.5" />
            <circle cx="15" cy="18" r="1.5" />
          </svg>
        </button>
        <label class="nav-config-toggle">
          <input
            type="checkbox"
            :checked="!item.hidden"
            :aria-label="`Show ${item.label} in the sidebar`"
            @change="setNavHidden(item.id, !$event.target.checked)"
          />
          <Icon :name="item.icon" />
          <span>{{ item.label }}</span>
        </label>
      </li>
    </ul>
  </section>
</template>
