// The sections of the Settings page. Shared so the page's tabs and the command
// palette's per-section jumps stay in sync from one definition. Each id is the
// `section` query value the page reads, so a palette entry can link straight to
// a section.

export const SETTINGS_SECTIONS = [
  { id: 'sessions', label: 'Session links', icon: 'link' },
  { id: 'tools', label: 'Local tools', icon: 'server' },
  { id: 'identity', label: 'Identity', icon: 'identity' },
  { id: 'slack', label: 'Slack', icon: 'server' },
  { id: 'harnesses', label: 'Agent harnesses', icon: 'harness' },
  { id: 'prompts', label: 'Agent prompts', icon: 'prompt' },
  { id: 'refresh', label: 'Refresh', icon: 'refresh' },
  { id: 'review-scan', label: 'Review requests', icon: 'search' },
  { id: 'groups', label: 'Repository groups', icon: 'group' },
  { id: 'sidebar', label: 'Sidebar', icon: 'panel' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'diagnostics' }
]
