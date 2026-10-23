// The sidebar's per-device state: desktop width, hidden/shown, and the
// mobile drawer's open/close swipe. Kept out of App.vue so the shell reads
// as layout and the gesture math lives on its own.
import { computed, onMounted, onUnmounted, ref } from 'vue'

export function useSidebar({ sidebarOpen, showNew, paletteOpen }) {
  // --- Sidebar drawer swipe ---------------------------------------------------
  // Below 760px the sidebar is an off-canvas drawer. Swiping right opens it and
  // swiping left while it is open closes it. An opening swipe is not restricted to
  // the screen edge: Android's own back gesture owns the outer few millimetres of
  // the edge and swallows a swipe that starts there, so the gesture starts
  // anywhere the page does not already use a sideways drag. Plain touch events,
  // never preventDefault, so vertical scrolling is untouched.
  const SIDEBAR_LOCK_PX = 12 // horizontal travel that claims the gesture
  const SIDEBAR_FLICK_MS = 250 // a quick swipe this short still commits
  const SIDEBAR_FLICK_PX = 24
  // While a swipe is in flight this is how far the drawer has been dragged
  // (0 closed, 1 open). It is null the rest of the time, when CSS owns the
  // transform; dragging holds the release back one frame so the transition runs.
  const sidebarDrag = ref(null)
  const sidebarDragging = ref(false)
  const sidebarDragStyle = computed(() =>
    sidebarDrag.value === null ? null : { transform: `translateX(${(sidebarDrag.value - 1) * 100}%)` }
  )
  let swipe = null
  let swipeSeq = 0

  // A sideways swipe that starts on a strip that scrolls sideways belongs to that
  // strip, and one that starts in a text field belongs to the caret. `.main` is
  // the page scroller itself, so it is never treated as a sideways strip.
  function gestureIsOwned(target) {
    if (!(target instanceof Element)) return false
    if (target.closest('input, textarea, [contenteditable]')) return true
    for (let node = target; node instanceof Element; node = node.parentElement) {
      if (node.classList.contains('main')) return false
      if (node.scrollWidth > node.clientWidth + 1) return true
    }
    return false
  }

  function beginSwipe(event) {
    // Only on the mobile layout, one finger, and never under a modal or palette.
    if (window.innerWidth > 760 || event.touches.length !== 1) return
    if (showNew.value || paletteOpen.value) return
    const opening = !sidebarOpen.value
    if (opening && gestureIsOwned(event.target)) return
    const touch = event.touches[0]
    swipe = {
      seq: ++swipeSeq,
      startX: touch.clientX,
      startY: touch.clientY,
      startTime: Date.now(),
      width: Math.max(window.innerWidth, 1),
      opening,
      decided: false,
      dx: 0,
      progress: opening ? 0 : 1
    }
  }

  function moveSwipe(event) {
    if (!swipe || event.touches.length !== 1) return
    const touch = event.touches[0]
    const dx = touch.clientX - swipe.startX
    const dy = touch.clientY - swipe.startY
    if (!swipe.decided) {
      // Wait until the finger has committed to a horizontal swipe in the useful
      // direction. Touch sampling drifts sideways early on, so one sideways
      // sample must not kill the gesture; only a drag whose sideways travel keeps
      // up with its horizontal travel (a page scroll) is left alone.
      const along = swipe.opening ? dx : -dx
      if (along < SIDEBAR_LOCK_PX || Math.abs(dy) >= along) return
      swipe.decided = true
      sidebarDragging.value = true
    }
    swipe.dx = dx
    const raw = swipe.opening ? dx / swipe.width : 1 + dx / swipe.width
    swipe.progress = Math.min(1, Math.max(0, raw))
    sidebarDrag.value = swipe.progress
  }

  function endSwipe() {
    if (!swipe) return
    const gesture = swipe
    swipe = null
    if (!gesture.decided) return
    const flick = Date.now() - gesture.startTime < SIDEBAR_FLICK_MS && Math.abs(gesture.dx) >= SIDEBAR_FLICK_PX
    const committed = flick || (gesture.opening ? gesture.progress > 0.5 : gesture.progress < 0.5)
    sidebarOpen.value = gesture.opening ? committed : !committed
    releaseDrawer(gesture.seq)
  }

  function cancelSwipe() {
    if (!swipe) return
    const seq = swipe.seq
    swipe = null
    releaseDrawer(seq)
  }

  // Let the drawer render at the released position with the transition back on,
  // then hand it back to CSS, so it eases from where the finger let go instead of
  // snapping.
  function releaseDrawer(seq) {
    sidebarDragging.value = false
    requestAnimationFrame(() => {
      if (swipeSeq === seq) sidebarDrag.value = null
    })
  }

  // --- Sidebar resize (desktop) ----------------------------------------------
  // On desktop the sidebar is a grid column of its own. A handle on its right
  // edge drags that column between a floor that keeps the list readable and a
  // ceiling that leaves the page usable. Width is a per-device preference, so it
  // is kept in localStorage rather than on the server.
  const SIDEBAR_DEFAULT_PX = 300
  // The floor keeps the Search / New task row and the nav icon row intact.
  const SIDEBAR_MIN_PX = 260
  const SIDEBAR_MAX_PX = 560
  const SIDEBAR_WIDTH_KEY = 'agentic.sidebarWidth'
  const SIDEBAR_HIDDEN_KEY = 'agentic.sidebarHidden'
  // Above this width the sidebar is a column; at or below it is a drawer.
  const DESKTOP_MIN_PX = 760
  const sidebarWidth = ref(readStoredWidth())
  const sidebarResizing = ref(false)
  const sidebarHidden = ref(readStoredNumber(SIDEBAR_HIDDEN_KEY) === 1)

  function isDesktop() {
    return window.innerWidth > DESKTOP_MIN_PX
  }

  function readStoredNumber(key) {
    try {
      const raw = localStorage.getItem(key)
      return raw === null ? null : Number(raw)
    } catch {
      // Storage can be blocked (private mode).
      return null
    }
  }

  function writeStored(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      // Not fatal: the choice still applies for this session.
    }
  }

  function readStoredWidth() {
    const stored = readStoredNumber(SIDEBAR_WIDTH_KEY)
    return stored !== null && stored > 0 ? clampSidebarWidth(stored) : SIDEBAR_DEFAULT_PX
  }

  function clampSidebarWidth(px) {
    return Math.round(Math.min(SIDEBAR_MAX_PX, Math.max(SIDEBAR_MIN_PX, px)))
  }

  function setSidebarWidth(px, persist = true) {
    sidebarWidth.value = clampSidebarWidth(px)
    if (!persist) return
    writeStored(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
  }

  function setSidebarHidden(hidden) {
    sidebarHidden.value = hidden
    writeStored(SIDEBAR_HIDDEN_KEY, hidden ? '1' : '0')
  }

  // The menu button toggles the drawer on mobile and reveals the column on
  // desktop, where it is only shown while the sidebar is hidden.
  function toggleSidebar() {
    if (isDesktop()) setSidebarHidden(!sidebarHidden.value)
    else sidebarOpen.value = !sidebarOpen.value
  }

  // Whether the task list is on screen, for the toggle's state and label.
  function sidebarExpanded() {
    return isDesktop() ? !sidebarHidden.value : sidebarOpen.value
  }

  function sidebarToggleLabel() {
    return sidebarExpanded() ? 'Hide the task list (⌘B)' : 'Show the task list (⌘B)'
  }

  let resizeFrom = null

  function startResize(event) {
    // Below 760px the sidebar is an off-canvas drawer, not a column to size.
    if (!isDesktop() || event.button > 0) return
    resizeFrom = { x: event.clientX, width: sidebarWidth.value }
    sidebarResizing.value = true
    window.addEventListener('pointermove', moveResize)
    window.addEventListener('pointerup', endResize)
    window.addEventListener('pointercancel', endResize)
    event.preventDefault()
  }

  function moveResize(event) {
    if (!resizeFrom) return
    // Not persisted until the drag ends, so a drag writes storage once.
    setSidebarWidth(resizeFrom.width + (event.clientX - resizeFrom.x), false)
  }

  function endResize() {
    if (!resizeFrom) return
    resizeFrom = null
    sidebarResizing.value = false
    window.removeEventListener('pointermove', moveResize)
    window.removeEventListener('pointerup', endResize)
    window.removeEventListener('pointercancel', endResize)
    setSidebarWidth(sidebarWidth.value)
  }

  function resetSidebarWidth() {
    setSidebarWidth(SIDEBAR_DEFAULT_PX)
  }

  // The handle is a separator the keyboard can drive: arrows nudge it, Home/End
  // jump to the bounds, Enter restores the default.
  function onResizerKeydown(event) {
    const step = event.shiftKey ? 40 : 10
    if (event.key === 'ArrowLeft') setSidebarWidth(sidebarWidth.value - step)
    else if (event.key === 'ArrowRight') setSidebarWidth(sidebarWidth.value + step)
    else if (event.key === 'Home') setSidebarWidth(SIDEBAR_MIN_PX)
    else if (event.key === 'End') setSidebarWidth(SIDEBAR_MAX_PX)
    else if (event.key === 'Enter') resetSidebarWidth()
    else return
    event.preventDefault()
  }

  onMounted(() => {
    window.addEventListener('touchstart', beginSwipe)
    window.addEventListener('touchmove', moveSwipe)
    window.addEventListener('touchend', endSwipe)
    window.addEventListener('touchcancel', cancelSwipe)
  })
  onUnmounted(() => {
    window.removeEventListener('touchstart', beginSwipe)
    window.removeEventListener('touchmove', moveSwipe)
    window.removeEventListener('touchend', endSwipe)
    window.removeEventListener('touchcancel', cancelSwipe)
    window.removeEventListener('pointermove', moveResize)
    window.removeEventListener('pointerup', endResize)
    window.removeEventListener('pointercancel', endResize)
  })

  return {
    SIDEBAR_MIN_PX,
    SIDEBAR_MAX_PX,
    sidebarWidth,
    sidebarResizing,
    sidebarHidden,
    sidebarDragStyle,
    sidebarDragging,
    toggleSidebar,
    sidebarExpanded,
    sidebarToggleLabel,
    startResize,
    onResizerKeydown,
    resetSidebarWidth
  }
}
