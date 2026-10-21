<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// The "Local tools" settings section: the base URLs of the ghx and slackx web
// UIs. When one is set, GitHub and Slack items link into that UI from the item
// detail page and the item lists. Like the other sections, the page shell owns
// the single settings read and this component saves each field on blur.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) }
})

const form = reactive({
  ghx_url: '',
  slackx_url: ''
})
const saving = ref(false)
const saved = ref(false)
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.ghx_url = overrides.ghx_url ?? ''
    form.slackx_url = overrides.slackx_url ?? ''
  },
  { immediate: true }
)

async function saveField(key) {
  saving.value = true
  try {
    await api.settings.update({ [key]: form[key] })
    await store.loadSettings().catch(() => {})
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Local tools</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      Base URLs of the ghx and slackx web UIs. When one is set, GitHub and Slack items show a link that opens them
      there. Leave a field blank to hide that link.
    </p>

    <div class="field">
      <label>ghx server URL</label>
      <input
        v-model="form.ghx_url"
        class="input"
        :placeholder="defaults.ghx_url || 'http://localhost:8080'"
        @blur="saveField('ghx_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The UI <code>ghx serve</code> starts (default port 8080). A GitHub issue or pull request opens at
        <code>&lt;url&gt;/#/&lt;owner&gt;/&lt;repo&gt;/&lt;issues|pulls&gt;/&lt;number&gt;</code>.
      </p>
    </div>
    <div class="field">
      <label>slackx server URL</label>
      <input
        v-model="form.slackx_url"
        class="input"
        :placeholder="defaults.slackx_url || 'http://localhost:8280'"
        @blur="saveField('slackx_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The UI <code>slackx serve</code> starts (default port 8280). A Slack thread opens at
        <code>&lt;url&gt;/archives/&lt;channel&gt;/p&lt;ts&gt;</code>.
      </p>
    </div>
  </section>
</template>
