// The sections of the Settings page. Shared so the page's tabs and the command
// palette's per-section jumps stay in sync from one definition. Each id is the
// `section` query value the page reads, so a palette entry can link straight to
// a section.

export const SETTINGS_SECTIONS = [
  { id: 'sessions', label: 'Session links', icon: 'link' },
  { id: 'tools', label: 'Local tools', icon: 'server' },
  { id: 'slack', label: 'Slack', icon: 'slack' },
  { id: 'github', label: 'GitHub', icon: 'github' },
  { id: 'harnesses', label: 'Agent harnesses', icon: 'harness' },
  { id: 'prompts', label: 'Agent prompts', icon: 'prompt' },
  { id: 'checklists', label: 'Checklists', icon: 'tasks' },
  { id: 'review-scan', label: 'Review requests', icon: 'search' },
  { id: 'groups', label: 'Repository groups', icon: 'group' },
  { id: 'sidebar', label: 'Sidebar', icon: 'panel' },
  { id: 'debug-bar', label: 'Debug bar', icon: 'terminal' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'diagnostics' }
]
