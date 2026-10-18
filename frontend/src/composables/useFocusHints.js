// Focus-hint mode: press f, then the letter over a control, to focus it. The
// targets are scanned from the page so every field/button is covered.
import { ref, watch } from 'vue'

import { store } from '../store'

const HINT_SELECTOR = 'a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])'

export function useFocusHints() {
  const hintBadges = ref([])
  let hintTargets = []
  let hintBuffer = ''
  let hintCleanup = null

  function hintLabelFor(index) {
    const alphabet = 'abcdefghijklmnopqrstuvwxyz'
    if (index < alphabet.length) return alphabet[index]
    const rest = index - alphabet.length
    return alphabet[Math.floor(rest / alphabet.length)] + alphabet[rest % alphabet.length]
  }

  // Dim the badges whose label does not start with what has been typed so far.
  function updateHintMatches() {
    hintTargets.forEach((target, index) => {
      const badge = hintBadges.value[index]
      if (badge) badge.dimmed = hintBuffer !== '' && !target.key.startsWith(hintBuffer)
    })
  }

  function focusHint(target) {
    target.el.focus()
    store.hintMode = false
  }

  function positionHints() {
    hintTargets.forEach((target, index) => {
      const badge = hintBadges.value[index]
      if (!badge) return
      const rect = target.el.getBoundingClientRect()
      badge.left = rect.left
      badge.top = rect.top
      badge.hidden = rect.width === 0 && rect.height === 0
    })
  }

  function stopHints() {
    hintCleanup?.()
    hintCleanup = null
    hintTargets = []
    hintBadges.value = []
    hintBuffer = ''
  }

  function startHints() {
    stopHints()
    const container = document.querySelector('.main')
    if (!container) return
    const nodes = Array.from(container.querySelectorAll(HINT_SELECTOR)).filter(
      // Skip the agent transcript and controls that opt out (the sidebar toggle).
      (el) => !el.disabled && !el.closest('.transcript') && !el.hasAttribute('data-no-hint')
    )
    hintTargets = nodes.map((el, index) => ({ key: hintLabelFor(index), el }))
    hintBadges.value = hintTargets.map(({ key }) => ({ key, left: 0, top: 0, hidden: false, dimmed: false }))
    positionHints()
    window.addEventListener('scroll', positionHints, true)
    window.addEventListener('resize', positionHints)
    hintCleanup = () => {
      window.removeEventListener('scroll', positionHints, true)
      window.removeEventListener('resize', positionHints)
    }
  }

  // Whether the page has any control the hints would cover (so `f` does something).
  function hasHintTargets() {
    return !!document.querySelector('.main')?.querySelector(`:is(${HINT_SELECTOR}):not([data-no-hint])`)
  }

  // Consume a key pressed while hint mode is on. Always claims the key so the
  // caller stops handling it (matching the inline handler this replaced).
  function handleHintKey(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      store.hintMode = false
      return true
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const exact = hintTargets.find((target) => target.key === hintBuffer)
      if (exact) focusHint(exact)
      return true
    }
    if (event.key === 'Backspace') {
      event.preventDefault()
      hintBuffer = hintBuffer.slice(0, -1)
      updateHintMatches()
      return true
    }
    const char = event.key.toLowerCase()
    if (/^[a-z]$/.test(char)) {
      event.preventDefault()
      const next = hintBuffer + char
      const matches = hintTargets.filter((target) => target.key.startsWith(next))
      if (matches.length === 1) {
        focusHint(matches[0])
      } else {
        hintBuffer = matches.length === 0 ? '' : next
        updateHintMatches()
      }
    }
    return true
  }

  watch(
    () => store.hintMode,
    (on) => (on ? startHints() : stopHints())
  )

  return { hintBadges, handleHintKey, hasHintTargets, stopHints }
}
