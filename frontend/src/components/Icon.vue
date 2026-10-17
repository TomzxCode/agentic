<script>
import { h } from 'vue'

// The glyphs the command palette shows in front of an item (and the sidebar
// nav, which shares the page glyphs). Each entry is the inner markup of a 24x24
// stroke icon, rendered with a render function so no v-html lands in templates.
const ICONS = {
  // Pages: the sidebar's bottom nav.
  tasks: [
    ['path', { d: 'M9 6h11M9 12h11M9 18h11' }],
    ['path', { d: 'M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2' }]
  ],
  inbox: [
    ['rect', { x: 4, y: 5.5, width: 16, height: 13, rx: 2 }],
    ['path', { d: 'M4.5 7.5l7.5 6 7.5-6' }]
  ],
  stack: [
    ['rect', { x: 4, y: 3.5, width: 16, height: 5, rx: 1.5 }],
    ['rect', { x: 4, y: 9.5, width: 16, height: 5, rx: 1.5 }],
    ['rect', { x: 4, y: 15.5, width: 16, height: 5, rx: 1.5 }]
  ],
  gantt: [['path', { d: 'M4 6h9M4 12h13M4 18h6' }]],
  graph: [
    ['circle', { cx: 6, cy: 6, r: 2.4 }],
    ['circle', { cx: 6, cy: 18, r: 2.4 }],
    ['circle', { cx: 18, cy: 12, r: 2.4 }],
    ['path', { d: 'M8.2 7.2 15.8 11M8.2 16.8 15.8 13' }]
  ],
  metrics: [['path', { d: 'M5 20V11M12 20V5M19 20v-6' }]],
  items: [
    ['path', { d: 'M4 13l2-7h12l2 7v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z' }],
    ['path', { d: 'M4 13h4l1.5 2h5L16 13h4' }]
  ],
  people: [
    ['circle', { cx: 9, cy: 8, r: 3 }],
    ['path', { d: 'M3 20c0-3 2.5-5 6-5s6 2 6 5' }],
    ['path', { d: 'M16 5.5a3 3 0 0 1 0 5.5M18 15c2 .6 3 1.9 3 4' }]
  ],
  repositories: [
    ['path', { d: 'M12 3l9 5-9 5-9-5 9-5z' }],
    ['path', { d: 'M3 13l9 5 9-5' }]
  ],
  settings: [
    [
      'path',
      {
        d: 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z'
      }
    ],
    ['circle', { cx: 12, cy: 12, r: 3 }]
  ],

  // Actions.
  plus: [['path', { d: 'M12 5v14M5 12h14' }]],
  keyboard: [
    ['rect', { x: 3, y: 6, width: 18, height: 12, rx: 2 }],
    ['path', { d: 'M7 10h.01M10 10h.01M14 10h.01M17 10h.01M8 14h8' }]
  ],
  panel: [
    ['rect', { x: 3, y: 4.5, width: 18, height: 15, rx: 2.6 }],
    ['path', { d: 'M9.1 5.4v13.2' }]
  ],
  close: [['path', { d: 'M6 6l12 12M18 6L6 18' }]],

  // Task fields.
  title: [['path', { d: 'M4 7V4h16v3M9 20h6M12 4v16' }]],
  description: [['path', { d: 'M3 6h18M3 10h14M3 14h18M3 18h14' }]],
  status: [['circle', { cx: 12, cy: 12, r: 8 }]],
  priority: [['path', { d: 'M6 21V4h11l-2 3.5L17 11H6' }]],
  deadline: [
    ['rect', { x: 4, y: 5, width: 16, height: 15, rx: 2 }],
    ['path', { d: 'M8 3v4M16 3v4M4 10h16' }]
  ],
  personPlus: [
    ['circle', { cx: 9, cy: 8, r: 3.2 }],
    ['path', { d: 'M3.5 20c0-3 2.3-5 5.5-5s5.5 2 5.5 5' }],
    ['path', { d: 'M18 8v6M15 11h6' }]
  ],
  personCheck: [
    ['circle', { cx: 9, cy: 8, r: 3.2 }],
    ['path', { d: 'M3.5 20c0-3 2.3-5 5.5-5h1.2' }],
    ['path', { d: 'M15 17l2 2 4-4' }]
  ],
  link: [
    ['path', { d: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71' }],
    ['path', { d: 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71' }]
  ],
  tag: [
    ['path', { d: 'M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z' }],
    ['circle', { cx: 7.5, cy: 7.5, r: 1 }]
  ]
}

export default {
  props: {
    name: { type: String, required: true },
    size: { type: Number, default: 18 }
  },
  render() {
    const children = (ICONS[this.name] || []).map(([tag, attrs]) => h(tag, attrs))
    return h(
      'svg',
      {
        width: this.size,
        height: this.size,
        viewBox: '0 0 24 24',
        'aria-hidden': 'true',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': 2,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round'
      },
      children
    )
  }
}
</script>
