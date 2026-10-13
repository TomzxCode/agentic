<script setup>
// The shared card every list row is built from, so repositories, people, items,
// and tasks all render with the same structure and spacing: a header row
// (leading control, title, trailing actions) followed by free-form body and
// meta lines.
//
// Slots:
//   select       the bulk-select control, shown before the body when selectable
//   lead         the leading control in the header (badge, icon, status picker)
//   title        the title, usually a link
//   title-extra  elements that belong next to the title (e.g. person chips)
//   actions      trailing header elements (badges, buttons)
//   default      body content
//   meta         the footer line
defineProps({
  // Renders the bulk-select layout: the #select control beside the card body.
  selectable: { type: Boolean, default: false },
  // Highlights the card as part of a selection.
  selected: { type: Boolean, default: false }
})
</script>

<template>
  <div class="item" :class="{ 'select-item': selectable, selected }">
    <slot v-if="selectable" name="select" />
    <div class="item-body">
      <div class="item-top">
        <slot name="lead" />
        <div class="title-group">
          <slot name="title" />
          <slot name="title-extra" />
        </div>
        <slot name="actions" />
      </div>
      <slot />
      <slot name="meta" />
    </div>
  </div>
</template>
