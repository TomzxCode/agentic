<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// The "Identity" settings section: the GitHub login that counts as "you". The
// page shell supplies the raw overrides and the effective (detected) login; this
// component keeps the editable field and saves it on blur.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  effective: { type: Object, default: () => ({}) }
})

const form = reactive({ github_login: '' })
const detectedLogin = ref('')
const saving = ref(false)
const saved = ref(false)
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.github_login = overrides.github_login ?? ''
    // Only show a detected value when the user has not overridden it.
    detectedLogin.value = overrides.github_login ? '' : props.effective?.github_login || ''
  },
  { immediate: true }
)

// Saving the login reloads the shared settings so the inbox and repository
// views see the new identity without a page reload.
async function save() {
  saving.value = true
  try {
    await api.settings.update({ github_login: form.github_login.trim() })
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
    await store.loadSettings().catch(() => {})
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
      <h2>Identity</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      The GitHub account that counts as you. The inbox and a repository's pull requests only offer to record a change
      for a merged PR this account authored.
    </p>
    <div class="field">
      <label>Your GitHub login</label>
      <input
        v-model="form.github_login"
        class="input"
        :placeholder="detectedLogin || 'detected from gh when blank'"
        @blur="save"
      />
      <p class="faint" style="margin: 4px 0 0">
        <template v-if="detectedLogin">
          Detected from <code>gh</code>: <code>{{ detectedLogin }}</code
          >.
        </template>
        Leave blank to use that, or set a login to override it.
      </p>
    </div>
  </section>
</template>
