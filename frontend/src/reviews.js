// Grouping for a PR's review reports, read from the user-global ~/.sdlc store.
//
// Everything here is pure: the item view hands it the files the reviews
// endpoint returned, so no request is involved.

// Group review report files by the commit they cover. The API orders files
// newest first, so groups keep that order (a group is positioned by its newest
// file) and the files inside a group stay newest first. Files with no commit in
// their name (a raw PR cache, a "no-issue" variant) collect in one ungrouped
// bucket whose commit is null.
export function groupReviewFiles(files) {
  const groups = []
  const byCommit = new Map()
  for (const file of files || []) {
    const key = file.commit || ''
    let group = byCommit.get(key)
    if (!group) {
      group = { commit: file.commit || null, files: [], updated_at: file.modified_at || null }
      byCommit.set(key, group)
      groups.push(group)
    }
    group.files.push(file)
    if (file.modified_at && (!group.updated_at || file.modified_at > group.updated_at)) {
      group.updated_at = file.modified_at
    }
  }
  return groups
}

// A report's label: the skill it ran (the part of "<skill>.<sha>.md" before the
// commit), or the file name without its ".md" suffix when it names no commit.
export function reviewLabel(file) {
  if (file?.skill) return file.skill
  return String(file?.name || '').replace(/\.md$/i, '')
}

// Each report opens with an HTML marker comment (`<!-- {"step":...} -->`) that
// the review orchestrator scans. GitHub hides an HTML comment, but the renderer
// escapes raw HTML (so nothing in a report can inject markup), which would show
// the marker as text. Strip a single leading marker to keep the body clean.
export function stripReportMarker(text) {
  return String(text || '').replace(/^\s*<!--[\s\S]*?-->\s*/, '')
}
