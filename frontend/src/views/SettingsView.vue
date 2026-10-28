<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { SETTINGS_SECTIONS } from '../settings'
import { store } from '../store'
import Icon from '../components/Icon.vue'
import RepositoryGroupsPanel from '../components/RepositoryGroupsPanel.vue'
import SettingsSessionLinks from '../components/SettingsSessionLinks.vue'
import SettingsToolServers from '../components/SettingsToolServers.vue'
import SettingsIdentity from '../components/SettingsIdentity.vue'
import SettingsSlack from '../components/SettingsSlack.vue'
import SettingsHarnesses from '../components/SettingsHarnesses.vue'
import SettingsPrompts from '../components/SettingsPrompts.vue'
import SettingsRefresh from '../components/SettingsRefresh.vue'
import SettingsReviewScan from '../components/SettingsReviewScan.vue'
import SettingsSidebar from '../components/SettingsSidebar.vue'
import SettingsDiagnostics from '../components/SettingsDiagnostics.vue'

const route = useRoute()
const router = useRouter()

const SECTIONS = SETTINGS_SECTIONS
const active = ref(SECTIONS.some((s) => s.id === route.query.section) ? route.query.section : SECTIONS[0].id)

function select(id) {
  active.value = id
  router.replace({ query: { section: id } })
}

watch(
  () => route.query.section,
  (section) => {
    if (SECTIONS.some((s) => s.id === section)) active.value = section
  }
)

// The one settings read the page makes. Each section below seeds its editable
// copy from these raw values and owns its own save state, so a section's edits
// never touch the others.
const settings = ref({ defaults: {}, overrides: {}, effective: {} })

async function loadSettings() {
  settings.value = await api.settings.get()
}

async function loadRepositories() {
  await store.loadRepositories().catch((e) => store.notify(e.message, true))
}

async function load() {
  await Promise.all([loadRepositories(), loadSettings().catch((e) => store.notify(e.message, true))])
}

onMounted(load)
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Settings</h1>

    <div class="settings-layout">
      <nav class="settings-nav">
        <button
          v-for="section in SECTIONS"
          :key="section.id"
          type="button"
          class="settings-nav-item"
          :class="{ active: active === section.id }"
          @click="select(section.id)"
        >
          <Icon :name="section.icon" :size="16" />
          <span>{{ section.label }}</span>
        </button>
      </nav>

      <div class="settings-content">
        <SettingsSessionLinks
          v-show="active === 'sessions'"
          :overrides="settings.overrides"
          :defaults="settings.defaults"
        />
        <SettingsToolServers
          v-show="active === 'tools'"
          :overrides="settings.overrides"
          :defaults="settings.defaults"
          :effective="settings.effective"
          :managed="settings.managed_tools || []"
          @changed="loadSettings"
        />
        <SettingsIdentity
          v-show="active === 'identity'"
          :overrides="settings.overrides"
          :effective="settings.effective"
        />
        <SettingsSlack v-show="active === 'slack'" :overrides="settings.overrides" :defaults="settings.defaults" />
        <SettingsHarnesses v-show="active === 'harnesses'" />
        <SettingsPrompts v-show="active === 'prompts'" :overrides="settings.overrides" :defaults="settings.defaults" />
        <SettingsRefresh
          v-show="active === 'refresh'"
          :overrides="settings.overrides"
          :defaults="settings.defaults"
          :active="active === 'refresh'"
        />
        <SettingsReviewScan
          v-show="active === 'review-scan'"
          :overrides="settings.overrides"
          :defaults="settings.defaults"
          :active="active === 'review-scan'"
        />

        <div v-show="active === 'groups'">
          <RepositoryGroupsPanel :repositories="store.repositories" />
        </div>

        <SettingsSidebar v-show="active === 'sidebar'" />
        <SettingsDiagnostics v-show="active === 'diagnostics'" :active="active === 'diagnostics'" />
      </div>
    </div>
  </div>
</template>
