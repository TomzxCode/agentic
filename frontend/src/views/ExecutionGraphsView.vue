<script setup>
import { ref } from 'vue'
import GraphsList from '../components/GraphsList.vue'
import GraphExecutions from '../components/GraphExecutions.vue'

// The execution graphs page: user-defined DAGs of agent runs and input forms,
// fired by hand or on a cron schedule. This shell owns the header, the tab
// switch, and the refresh button; each tab is its own component.
const tab = ref('graphs')
// Reported by the tabs, for the header count and Refresh button.
const graphCount = ref(0)
const executionCount = ref(0)
const graphsLoading = ref(true)
const executionsLoading = ref(false)
// Bumped to ask the active tab to reload.
const refreshToken = ref(0)

// A run started anywhere flips to the executions tab, where the progress is.
function onRunStarted() {
  tab.value = 'executions'
  refreshToken.value += 1
}
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Execution graphs</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span class="faint">
          {{
            tab === 'graphs'
              ? `${graphCount} graph${graphCount === 1 ? '' : 's'}`
              : `${executionCount} execution${executionCount === 1 ? '' : 's'}`
          }}
        </span>
        <button
          class="btn sm ghost"
          :disabled="tab === 'graphs' ? graphsLoading : executionsLoading"
          @click="refreshToken += 1"
        >
          <span v-if="tab === 'graphs' ? graphsLoading : executionsLoading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>

    <div class="row graphs-tabs" role="tablist" aria-label="Execution graphs views">
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'graphs' }"
        role="tab"
        :aria-selected="tab === 'graphs'"
        @click="tab = 'graphs'"
      >
        Graphs
      </button>
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'executions' }"
        role="tab"
        :aria-selected="tab === 'executions'"
        @click="tab = 'executions'"
      >
        Executions
      </button>
    </div>

    <GraphsList
      v-show="tab === 'graphs'"
      :active="tab === 'graphs'"
      :refresh-token="refreshToken"
      @count="graphCount = $event"
      @loading="graphsLoading = $event"
      @run-started="onRunStarted"
    />

    <GraphExecutions
      v-show="tab === 'executions'"
      :active="tab === 'executions'"
      :refresh-token="refreshToken"
      @count="executionCount = $event"
      @loading="executionsLoading = $event"
    />
  </div>
</template>

<style scoped>
.graphs-tabs {
  gap: 6px;
  margin-bottom: 12px;
}
</style>
