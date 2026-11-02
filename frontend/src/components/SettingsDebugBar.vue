<script setup>
import Icon from './Icon.vue'
import { debugBarVisible, setDebugBarVisible } from '../debugBar'

// The "Debug bar" settings section: whether the bar pinned to the bottom of
// every page is shown. A per-device choice in localStorage (owned by
// debugBar.js), so there is no server round trip and no save button. The rest
// of what the bar shows (the details panel, its tabs, its height) stays on the
// bar itself.
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Debug bar</h2>
    </div>
    <p class="faint" style="margin-top: 0">
      The bar pinned to the bottom of every page shows how many API calls and database queries the page has made. Turn
      it off to get the bottom of the window back; page-load timings and the request log stay behind its
      <span class="mono">Show details</span> button while it is on.
    </p>

    <label class="nav-config-toggle">
      <input
        type="checkbox"
        :checked="debugBarVisible"
        data-testid="debug-bar-toggle"
        aria-label="Show the debug bar"
        @change="setDebugBarVisible($event.target.checked)"
      />
      <Icon name="diagnostics" />
      <span>Show the debug bar</span>
    </label>
    <p class="faint" style="margin-bottom: 0">
      Saved on this device. Turning the bar off here is the only way back, so it stays reachable from Settings.
    </p>
  </section>
</template>
