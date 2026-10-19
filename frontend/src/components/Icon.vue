<script>
import { h } from 'vue'

// The glyphs the command palette shows in front of an item (and the sidebar
// nav, which shares the page glyphs). Each entry is the inner markup of a 24x24
// stroke icon, rendered with a render function so no v-html lands in templates.
const ICONS = {
  // Pages: the sidebar's bottom nav. Each page keeps one silhouette that the
  // others do not use, so the twelve stay apart at 18px: Tasks a checklist,
  // Inbox a mail tray, Reviews a document, Stack layers, Gantt and Metrics a
  // chart (bars against a trend line), Items a box, Graph a node network,
  // People a pair, Repositories a book, Schedules a clock, Settings a gear.
  tasks: [
    ['path', { d: 'M10 5.5h9.5M10 12h9.5M10 18.5h9.5' }],
    ['path', { d: 'M3.5 5.2l1.6 1.6 3-3.2' }],
    ['path', { d: 'M3.5 11.7l1.6 1.6 3-3.2' }],
    ['path', { d: 'M3.5 18.2l1.6 1.6 3-3.2' }]
  ],
  inbox: [
    ['polyline', { points: '21 12 15.6 12 13.8 14.7 10.2 14.7 8.4 12 3 12' }],
    [
      'path',
      {
        d: 'M6.1 5.8 3 12v5.4a1.8 1.8 0 0 0 1.8 1.8h14.4a1.8 1.8 0 0 0 1.8-1.8v-5.4l-3.11-6.2A1.8 1.8 0 0 0 16.28 4.8H7.72a1.8 1.8 0 0 0-1.61 1z'
      }
    ]
  ],
  reviews: [
    ['path', { d: 'M13.5 3H7.5a2.5 2.5 0 0 0-2.5 2.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8.5z' }],
    ['path', { d: 'M13.5 3v4a1.5 1.5 0 0 0 1.5 1.5h4' }],
    ['path', { d: 'M9.5 14.6l1.9 1.9 3.6-3.8' }]
  ],
  stack: [
    ['path', { d: 'M12 3.4 20.5 7.9 12 12.4 3.5 7.9z' }],
    ['path', { d: 'M3.5 12l8.5 4.5 8.5-4.5' }],
    ['path', { d: 'M3.5 16.1l8.5 4.5 8.5-4.5' }]
  ],
  gantt: [
    ['path', { d: 'M10 6.5h7.5' }],
    ['path', { d: 'M7 11.5h7' }],
    ['path', { d: 'M12 16.5h5.5' }],
    ['path', { d: 'M3.5 3.5v14.5a2.5 2.5 0 0 0 2.5 2.5h14.5' }]
  ],
  graph: [
    ['circle', { cx: 6, cy: 6, r: 2.4 }],
    ['circle', { cx: 6, cy: 18, r: 2.4 }],
    ['circle', { cx: 18, cy: 12, r: 2.4 }],
    ['path', { d: 'M8.2 7.2 15.8 11M8.2 16.8 15.8 13' }]
  ],
  metrics: [
    ['path', { d: 'M3.5 3.5v14.5a2.5 2.5 0 0 0 2.5 2.5h14.5' }],
    ['path', { d: 'M7 15.5l3.5-3.8 3 2.6 5.5-6' }]
  ],
  schedule: [
    ['circle', { cx: 12, cy: 12, r: 8.5 }],
    ['path', { d: 'M12 6.8V12l3.5 2.2' }]
  ],
  items: [
    ['path', { d: 'M3.7 7.4 12 3.2l8.3 4.2v9.2L12 20.8 3.7 16.6z' }],
    ['path', { d: 'M3.9 7.5 12 11.8l8.1-4.3M12 11.8v8.9' }]
  ],
  people: [
    ['circle', { cx: 9, cy: 8, r: 3 }],
    ['path', { d: 'M3 20c0-3 2.5-5 6-5s6 2 6 5' }],
    ['path', { d: 'M16 5.5a3 3 0 0 1 0 5.5M18 15c2 .6 3 1.9 3 4' }]
  ],
  repositories: [['path', { d: 'M4.5 19.2V4.8A1.8 1.8 0 0 1 6.3 3h13.2v18H6.3a1.8 1.8 0 0 1 0-3.6h13.2' }]],
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
