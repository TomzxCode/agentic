import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// WorktreesPanel renders a <router-link>; stub it so mounting does not warn
// about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  taskUpdate: vi.fn(),
  associate: vi.fn(),
  unassociate: vi.fn(),
  itemRefresh: vi.fn(),
  itemUpdate: vi.fn(),
  worktreeCreate: vi.fn(),
  worktreeRemove: vi.fn(),
  refreshContext: vi.fn(),
  refreshSummary: vi.fn(),
  settingsGet: vi.fn(),
  changeCreate: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.taskUpdate, associate: mocks.associate, unassociate: mocks.unassociate },
    items: { refresh: mocks.itemRefresh, update: mocks.itemUpdate },
    worktrees: { create: mocks.worktreeCreate, remove: mocks.worktreeRemove },
    runs: { refreshContext: mocks.refreshContext, refreshSummary: mocks.refreshSummary },
    settings: { get: mocks.settingsGet },
    changes: { create: mocks.changeCreate }
  }
}))

import ItemsPanel from '../components/ItemsPanel.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ItemsPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    associations: [
      {
        id: 'a1',
        note: 'a note',
        created_at: new Date().toISOString(),
        item: { id: 'i1', source: 'github', title: 'Issue 1', url: 'https://x', content: 'body', fetched_at: null }
      }
    ],
    ...over
  })

  it('groups items by source and shows notes', () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('GitHub')
    expect(wrapper.text()).toContain('Issue 1')
    expect(wrapper.text()).toContain('a note')
  })

  it('does nothing when the draft is empty', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).not.toHaveBeenCalled()
  })

  it('associates a new item and clears the draft', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://github.com/o/r/issues/2')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ item: expect.objectContaining({ url: 'https://github.com/o/r/issues/2' }) })
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.findAll('input')[0].element.value).toBe('')
  })

  it('notifies when associating fails', async () => {
    mocks.associate.mockRejectedValueOnce(new Error('bad'))
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://x')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'bad', isError: true })
  })

  it('removes and refreshes an item', async () => {
    mocks.unassociate.mockResolvedValue({})
    mocks.itemRefresh.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })

    await wrapper.get('button[title="Remove"]').trigger('click')
    await flushPromises()
    expect(mocks.unassociate).toHaveBeenCalledWith('t1', 'i1')

    await wrapper.get('button[title="Refresh"]').trigger('click')
    await flushPromises()
    expect(mocks.itemRefresh).toHaveBeenCalledWith('i1')
  })

  it('opens any linked item that has a link in a new tab', () => {
    const withLinks = task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i1',
            source: 'github',
            kind: 'issue',
            title: 'Login fails',
            url: 'https://github.com/o/r/issues/2',
            content: '',
            fetched_at: null
          }
        },
        {
          id: 'a2',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i2',
            source: 'slack',
            title: 'Thread about login',
            url: 'https://acme.slack.com/archives/C1/p123',
            content: '',
            fetched_at: null
          }
        },
        {
          id: 'a3',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i3',
            source: 'gdrive',
            title: 'Design doc',
            url: 'https://docs.google.com/document/d/abc',
            content: '',
            fetched_at: null
          }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withLinks } })
    const links = wrapper.findAll('a[title="Open link"]')
    expect(links).toHaveLength(3)
    expect(links[0].attributes('href')).toBe('https://github.com/o/r/issues/2')
    expect(links[1].attributes('href')).toBe('https://acme.slack.com/archives/C1/p123')
    expect(links[2].attributes('href')).toBe('https://docs.google.com/document/d/abc')
    expect(links[0].attributes('target')).toBe('_blank')
    expect(links[0].attributes('rel')).toBe('noopener')
  })

  it('shows no link icon for an item that has no URL', () => {
    const withoutUrl = task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: { id: 'i1', source: 'note', title: 'Just a note', url: null, content: 'kept text', fetched_at: null }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withoutUrl } })
    expect(wrapper.find('a[title="Open link"]').exists()).toBe(false)
  })

  it('toggles the expanded state', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    const expand = wrapper.get('button[title="Expand"]')
    expect(expand.text()).toBe('▸')
    await expand.trigger('click')
    expect(wrapper.get('button[title="Expand"]').text()).toBe('▾')
  })

  it('shows the status of a pull request item', () => {
    const withPr = task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i1',
            source: 'github',
            kind: 'pull_request',
            title: 'Fix the thing',
            url: 'https://gh/pull/3',
            content: '',
            metadata_json: { state: 'OPEN', is_draft: true },
            fetched_at: null
          }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withPr } })
    expect(wrapper.text()).toContain('pull request')
    expect(wrapper.get('.badge.st-draft').text()).toBe('Draft')
  })

  const prTask = (over = {}) =>
    task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i1',
            source: 'github',
            kind: 'pull_request',
            title: 'Fix the thing',
            url: 'https://gh/pull/3',
            external_id: 'o/r#3',
            content: '',
            metadata_json: { state: 'OPEN' },
            fetched_at: null
          }
        }
      ],
      ...over
    })

  it('offers to record a change for a PR no change references yet', async () => {
    mocks.changeCreate.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: prTask() } })
    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()
    expect(mocks.changeCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Fix the thing',
      external_ref: 'https://gh/pull/3'
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('opens a merged PR as an accepted change dated to the merge', async () => {
    mocks.changeCreate.mockResolvedValue({})
    const merged = prTask()
    merged.associations[0].item.metadata_json = { state: 'MERGED', merged_at: '2026-10-11T05:23:53Z' }
    const wrapper = mount(ItemsPanel, { props: { task: merged } })
    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()
    expect(mocks.changeCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Fix the thing',
      external_ref: 'https://gh/pull/3',
      status: 'accepted',
      opened_at: '2026-10-11T05:23:53Z',
      accepted_at: '2026-10-11T05:23:53Z'
    })
  })

  it('hides the record button when a change already references the PR', () => {
    const wrapper = mount(ItemsPanel, {
      props: { task: prTask({ changes: [{ id: 'c1', external_ref: 'https://gh/pull/3' }] }) }
    })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('matches a change recorded against the PR external id', () => {
    const wrapper = mount(ItemsPanel, {
      props: { task: prTask({ changes: [{ id: 'c1', external_ref: 'o/r#3' }] }) }
    })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('does not offer a change for a non-PR item', () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('leaves notes to the Notes panel', () => {
    const withNote = task({
      associations: [
        ...task().associations,
        {
          id: 'a2',
          note: '',
          created_at: new Date().toISOString(),
          item: { id: 'i2', source: 'note', title: 'Just a note', url: null, content: 'kept text', fetched_at: null }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withNote } })
    expect(wrapper.text()).toContain('GitHub')
    expect(wrapper.text()).not.toContain('Just a note')
    expect(wrapper.text()).not.toContain('kept text')
  })
})
