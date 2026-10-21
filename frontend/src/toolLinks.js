// Links into the local ghx and slackx web UIs. Everything here is pure.
//
// Both tools serve a read-only browser UI over their cache:
//   ghx serve    -> #/{owner}/{repo}/{issues|pulls}/{number}
//   slackx serve -> /archives/{channel}/p{ts}?thread_ts={ts}
//
// The base URLs come from Settings (store.settings.ghx_url / slackx_url). An
// item links into the matching UI only when its source has one configured.

const GITHUB_ITEM_RE = /github\.com\/([^/\s]+)\/([^/\s?#]+)\/(issues|pull)\/(\d+)/i
// A GitHub https or ssh remote, tolerating a trailing ".git" and a query.
const GITHUB_REPO_RE = /github\.com[/:]([^/\s]+)\/([^/\s#?]+?)(?:\.git)?(?:[/\s#?]|$)/i
const SLACK_ITEM_RE = /\/archives\/([^/\s?#]+)\/p(\d{6,})/i
const SLACK_THREAD_TS_RE = /[?&]thread_ts=(\d{6,}\.\d+)/i
const SLACK_EXTERNAL_ID_RE = /^([^:\s]+):(\d{6,})$/

function trimBase(base) {
  return String(base || '')
    .trim()
    .replace(/\/+$/, '')
}

// A Slack ts as the dotted form the web UI takes, or "" when it is not one.
function slackTs(stamp) {
  return stamp.length > 10 ? `${stamp.slice(0, 10)}.${stamp.slice(10)}` : ''
}

// A GitHub issue/PR target in the casing its URL uses: ghx keys its cache by
// the repository's own casing, and route matching is case-sensitive.
export function githubItemTarget(url) {
  const match = GITHUB_ITEM_RE.exec(String(url || ''))
  if (!match) return null
  return {
    owner: match[1],
    repo: match[2].replace(/\.git$/i, ''),
    kind: match[3].toLowerCase() === 'pull' ? 'pulls' : 'issues',
    number: match[4]
  }
}

// A `{channel, stamp, threadTs}` Slack target from the item's permalink, or
// from its `channel:ts` external id when the permalink is not parseable.
export function slackItemTarget(item) {
  const fromUrl = SLACK_ITEM_RE.exec(String(item?.url || ''))
  if (fromUrl) {
    const stamp = fromUrl[2]
    // A reply permalink names the thread root in its query string; the p segment
    // is then the reply to highlight, not the root to open.
    const root = SLACK_THREAD_TS_RE.exec(String(item.url))
    return { channel: fromUrl[1], stamp, threadTs: root ? root[1] : slackTs(stamp) }
  }
  const fromId = SLACK_EXTERNAL_ID_RE.exec(String(item?.external_id || ''))
  if (fromId) {
    const stamp = fromId[2]
    return { channel: fromId[1], stamp, threadTs: slackTs(stamp) }
  }
  return null
}

// A registered repository's page in the ghx web UI, or null when there is no
// server or the remote is not GitHub.
export function ghxRepoUrl(remote, base) {
  const root = trimBase(base)
  const match = GITHUB_REPO_RE.exec(String(remote || ''))
  if (!root || !match) return null
  return `${root}/#/${encodeURIComponent(match[1])}/${encodeURIComponent(match[2])}`
}

// The item's page in the ghx web UI, or null when there is no server or the
// item is not a GitHub issue/PR.
export function ghxItemUrl(item, base) {
  const root = trimBase(base)
  const target = githubItemTarget(item?.url)
  if (!root || !target) return null
  const owner = encodeURIComponent(target.owner)
  const repo = encodeURIComponent(target.repo)
  return `${root}/#/${owner}/${repo}/${target.kind}/${target.number}`
}

// The item's thread in the slackx web UI, or null when there is no server or
// the item is not a Slack thread.
export function slackxItemUrl(item, base) {
  const root = trimBase(base)
  const target = slackItemTarget(item)
  if (!root || !target) return null
  const channel = encodeURIComponent(target.channel)
  const thread = target.threadTs ? `?thread_ts=${encodeURIComponent(target.threadTs)}` : ''
  return `${root}/archives/${channel}/p${target.stamp}${thread}`
}

// Every local-tool link the item has, in display order.
export function itemToolLinks(item, settings) {
  const links = []
  const ghx = item?.source === 'github' ? ghxItemUrl(item, settings?.ghx_url) : null
  if (ghx) links.push({ id: 'ghx', label: 'Open in ghx', url: ghx })
  const slackx = item?.source === 'slack' ? slackxItemUrl(item, settings?.slackx_url) : null
  if (slackx) links.push({ id: 'slackx', label: 'Open in slackx', url: slackx })
  return links
}
