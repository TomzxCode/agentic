// Which sidebar the shell renders: the full one (task list plus the page icons)
// or the thin icon rail that drops the task list. A per-device preference
// (localStorage), like the sidebar width, so it never touches the server's
// settings table. The state is module-level because the shell renders the
// sidebar while the Settings section switches it, and both must see the same
// choice without a reload.
import { computed, reactive } from 'vue'

const STORAGE_KEY = 'agentic.sidebarLayout'

// The rail's width: one icon column, wide enough for an 18px icon and the
// button's own padding.
export const SIDEBAR_RAIL_PX = 56

const state = reactive({ layout: 'full' })

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be blocked (private mode): the full sidebar is the default.
    return null
  }
}

// Read the stored choice into the state; the shell calls this before its first
// render so the rail never flashes the full sidebar.
export function loadSidebarLayout() {
  state.layout = readStored() === 'rail' ? 'rail' : 'full'
}

export function setSidebarLayout(layout) {
  state.layout = layout === 'rail' ? 'rail' : 'full'
  try {
    localStorage.setItem(STORAGE_KEY, state.layout)
  } catch {
    // Not fatal: the choice still applies for this session.
  }
}

export function toggleSidebarLayout() {
  setSidebarLayout(state.layout === 'rail' ? 'full' : 'rail')
}

export const sidebarLayout = computed(() => state.layout)
export const sidebarIsRail = computed(() => state.layout === 'rail')
