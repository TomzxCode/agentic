<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store } from '../store'

// The person-creation page a grey, unresolved handle links to: the handle is
// carried in the query as the prefilled name and alias, so creating the person
// resolves every listing that shows that handle.

const route = useRoute()
const router = useRouter()

// The handle a listing could not resolve, if this page was reached from one.
const sourceHandle = computed(() => String(route.query.alias || route.query.name || '').trim())

const name = ref(sourceHandle.value)
const aliasesText = ref(sourceHandle.value)
const notes = ref('')
const saving = ref(false)

// The aliases, split on commas, trimmed, without blanks or case-insensitive
// duplicates, matching how the API normalizes them.
const aliases = computed(() => {
  const seen = new Set()
  const result = []
  for (const part of aliasesText.value.split(',')) {
    const value = part.trim()
    if (!value) continue
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(value)
  }
  return result
})

const canCreate = computed(() => !!name.value.trim() && !saving.value)

async function create() {
  if (!canCreate.value) return
  saving.value = true
  try {
    const person = await api.people.create({
      name: name.value.trim(),
      aliases: aliases.value,
      notes: notes.value
    })
    await store.loadPeople().catch(() => {})
    store.notify('Person created')
    router.push(`/person/${person.id}`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <router-link class="btn sm ghost" to="/people" style="margin-bottom: 12px">← People</router-link>

    <h1 style="margin: 0 0 4px">New person</h1>
    <p v-if="sourceHandle" class="faint" style="margin: 0 0 16px">
      No person carries “{{ sourceHandle }}” yet. Create them and every listing that shows this handle links to their
      page.
    </p>

    <section class="panel">
      <div class="field">
        <label for="person-name">Name</label>
        <input id="person-name" v-model="name" class="input" placeholder="Full name" @keyup.enter="create" />
      </div>
      <div class="field">
        <label for="person-aliases">Aliases</label>
        <input
          id="person-aliases"
          v-model="aliasesText"
          class="input"
          placeholder="Comma-separated handles or emails…"
        />
        <div class="faint" style="margin-top: 4px">
          Aliases are the handles the person is matched by across sources, such as a GitHub login.
        </div>
      </div>
      <div class="field" style="margin-bottom: 0">
        <label for="person-notes">Notes</label>
        <textarea id="person-notes" v-model="notes" class="textarea" rows="3" placeholder="Optional notes" />
      </div>
    </section>

    <div class="row" style="gap: 8px; margin-top: 16px">
      <button class="btn primary" :disabled="!canCreate" @click="create">
        <span v-if="saving" class="spinner" aria-hidden="true"></span>
        {{ saving ? 'Creating…' : 'Create person' }}
      </button>
      <router-link class="btn sm ghost" to="/people">Cancel</router-link>
    </div>
  </div>
</template>
