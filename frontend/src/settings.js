// The sections of the Settings page. Shared so the page's tabs and the command
// palette's per-section jumps stay in sync from one definition. Each id is the
// `section` query value the page reads, so a palette entry can link straight to
// a section.

export const SETTINGS_SECTIONS = [
  { id: 'sessions', label: 'Session links' },
  { id: 'identity', label: 'Identity' },
  { id: 'harnesses', label: 'Agent harnesses' },
  { id: 'prompts', label: 'Agent prompts' },
  { id: 'refresh', label: 'Refresh' },
  { id: 'review-scan', label: 'Review requests' },
  { id: 'groups', label: 'Repository groups' },
  { id: 'sidebar', label: 'Sidebar' }
]
