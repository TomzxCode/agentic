import { computed, nextTick, ref, watch } from 'vue'
import { store } from '../store'
import { applyMention, buildMentionOptions, findMentionQuery } from '../mentions'

// @-mention autocomplete for a text field. The caller owns the value and the
// textarea element; this tracks the mention being typed, offers matching
// people, items, and relative dates, and inserts the chosen reference at the
// caret.
export function useMentions({ value, input }) {
  const open = ref(false)
  const query = ref('')
  const highlighted = ref(0)
  // The `@query` range the chosen option replaces.
  const token = ref(null)

  const options = computed(() =>
    open.value ? buildMentionOptions({ people: store.people, items: store.items, query: query.value }) : []
  )

  // A fresh search starts at the top of the list; a shorter result list never
  // leaves the highlight past its end.
  watch(query, () => {
    highlighted.value = 0
  })
  watch(options, (list) => {
    if (highlighted.value >= list.length) highlighted.value = Math.max(0, list.length - 1)
  })

  function close() {
    open.value = false
    query.value = ''
    token.value = null
    highlighted.value = 0
  }

  // Re-read the mention at the caret. Called on every input and caret move, so
  // backtracking out of a mention closes the picker.
  function refresh() {
    const el = input.value
    if (!el || typeof el.selectionStart !== 'number') {
      close()
      return
    }
    const found = findMentionQuery(el.value, el.selectionStart)
    if (!found) {
      close()
      return
    }
    // Only offer a picker when there is something to pick, and stop once the
    // typed text already spells a whole name: at that point the mention is
    // written and the rest of the line is prose (this is also what keeps an
    // inserted plain `@Ada Lovelace` from reopening the picker). A date phrase
    // is different: `@last week` is exactly what the user types before
    // choosing, and the field then stores the date instead, so it stays open.
    const matches = buildMentionOptions({ people: store.people, items: store.items, query: found.query })
    const typed = found.query.trim().toLowerCase()
    const spellsName = !matches.some((option) => option.kind === 'date')
    if (!matches.length || (spellsName && matches.some((option) => option.label.toLowerCase() === typed))) {
      close()
      return
    }
    token.value = found
    query.value = found.query
    if (!open.value) {
      open.value = true
      highlighted.value = 0
    }
  }

  function onInput() {
    refresh()
  }

  function onClick() {
    refresh()
  }

  // Returns true when the mention picker took the key, so the field's own
  // keydown handling (commit, cancel, submit) does not also run.
  function onKeydown(event) {
    if (!open.value) return false
    const list = options.value
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      highlighted.value = list.length ? (highlighted.value + 1) % list.length : 0
      return true
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      highlighted.value = list.length ? (highlighted.value - 1 + list.length) % list.length : 0
      return true
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation?.()
      close()
      return true
    }
    // Enter and Tab take the highlighted reference; the modifier forms keep
    // their own meaning (Ctrl/Cmd+Enter submits, Shift+Enter is a newline).
    if (
      (event.key === 'Enter' || event.key === 'Tab') &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey
    ) {
      const option = list[highlighted.value]
      if (!option) return false
      event.preventDefault()
      choose(option)
      return true
    }
    return false
  }

  function choose(option) {
    const el = input.value
    const current = token.value
    if (!el || !current) {
      close()
      return
    }
    const result = applyMention(String(value.value ?? ''), current, option)
    value.value = result.value
    close()
    nextTick(() => {
      el.focus()
      if (el.setSelectionRange) el.setSelectionRange(result.caret, result.caret)
    })
  }

  return { open, options, query, highlighted, onInput, onClick, onKeydown, choose, close, refresh }
}
