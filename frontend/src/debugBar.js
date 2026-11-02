// Whether the debug bar (the status bar pinned to the bottom of the page) is
// shown. A per-device preference (localStorage), like the sidebar width, so it
// never touches the server's settings table: a phone does not need the bar just
// because a desktop turned it on. The state is module-level because the shell
// renders the bar while the Settings section toggles it, so both must see the
// same choice without a reload.
import { computed, reactive } from 'vue'

const STORAGE_KEY = 'agentic.debugBarHidden'

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    // Storage can be blocked (private mode): show the bar, which is the default.
    return false
  }
}

const state = reactive({ hidden: readStored() })

export const debugBarVisible = computed(() => !state.hidden)

export function setDebugBarHidden(hidden) {
  state.hidden = Boolean(hidden)
  try {
    localStorage.setItem(STORAGE_KEY, state.hidden ? '1' : '0')
  } catch {
    // Not fatal: the choice still applies for this session.
  }
}

export function setDebugBarVisible(visible) {
  setDebugBarHidden(!visible)
}
