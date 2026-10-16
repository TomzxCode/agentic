import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import EntityCard from '../components/EntityCard.vue'
import ItemCard from '../components/ItemCard.vue'
import ItemLink from '../components/ItemLink.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskLink from '../components/TaskLink.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

beforeEach(() => {
  store.personFilter = ''
  store.tagFilter = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EntityCard', () => {
  it('renders the shared card layout from its slots', () => {
    const wrapper = mount(EntityCard, {
      slots: {
        lead: '<span class="lead">L</span>',
        title: '<span class="title">T</span>',
        'title-extra': '<span class="extra">E</span>',
        actions: '<button>A</button>',
        default: '<div class="body">B</div>',
        meta: '<div class="meta">M</div>'
      }
    })
    expect(wrapper.classes()).toContain('item')
    expect(wrapper.find('.item-top .lead').exists()).toBe(true)
    expect(wrapper.get('.title-group .title').text()).toBe('T')
    expect(wrapper.find('.title-group .extra').exists()).toBe(true)
    expect(wrapper.find('.item-top button').exists()).toBe(true)
    expect(wrapper.find('.body').exists()).toBe(true)
    expect(wrapper.find('.meta').exists()).toBe(true)
  })

  it('renders the bulk-select layout when selectable and highlights a selection', () => {
    const wrapper = mount(EntityCard, {
      props: { selectable: true, selected: true },
      slots: { select: '<input class="row-check" type="checkbox" />' }
    })
    expect(wrapper.classes()).toContain('select-item')
    expect(wrapper.classes()).toContain('selected')
    expect(wrapper.get('.row-check').exists()).toBe(true)
  })
})

describe('ItemCard', () => {
  const item = (over = {}) => ({
    id: 'i1',
    source: 'github',
    kind: 'issue',
    title: 'Issue one',
    url: 'https://gh/1',
    content: 'body',
    created_at: new Date().toISOString(),
    fetched_at: null,
    ...over
  })

  it('renders the source label, title link, kind, content, and times', () => {
    const wrapper = mount(ItemCard, { props: { item: item() }, ...stub })
    expect(wrapper.get('.chip-source').text()).toBe('GitHub')
    expect(wrapper.get('a.title').attributes('href')).toBe('https://gh/1')
    expect(wrapper.text()).toContain('issue')
    expect(wrapper.get('.content').text()).toBe('body')
    expect(wrapper.text()).toContain('added just now')
  })

  it('opens the item view when a `to` target is given', () => {
    const wrapper = mount(ItemCard, { props: { item: item(), to: '/items/i1' }, ...stub })
    expect(wrapper.get('a.title').attributes('href')).toBe('/items/i1')
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  })

  it('shows the GitHub state badge of a pull request', () => {
    const wrapper = mount(ItemCard, {
      props: { item: item({ kind: 'pull_request', metadata_json: { state: 'MERGED' } }) }
    })
    expect(wrapper.get('.badge.st-merged').text()).toBe('Merged')
  })

  it('hides the source badge and clamps the content when asked', () => {
    const wrapper = mount(ItemCard, {
      props: { item: item(), showSource: false, expanded: false }
    })
    expect(wrapper.find('.chip-source').exists()).toBe(false)
    expect(wrapper.get('.content').classes()).toContain('clamp')
  })
})

describe('TaskCard', () => {
  const task = (over = {}) => ({
    id: 't1',
    title: 'Task One',
    status: 'open',
    priority: 3,
    next_steps: [{ text: 'do it', done: false }],
    tags: ['bug'],
    updated_at: null,
    ...over
  })

  it('renders the status picker, priority, title, next step, and tags', () => {
    const wrapper = mount(TaskCard, { props: { task: task() }, ...stub })
    expect(wrapper.get('.task-status-select').exists()).toBe(true)
    expect(wrapper.get('.task-priority').classes()).toContain('prio-urgent')
    expect(wrapper.get('a.title').attributes('href')).toBe('/task/t1')
    expect(wrapper.text()).toContain('Next: do it')
    expect(wrapper.get('.tag-chip').text()).toBe('bug')
  })

  it('emits the chosen status', async () => {
    const wrapper = mount(TaskCard, { props: { task: task() }, ...stub })
    await wrapper.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((option) => option.text().includes('Blocked'))
      .trigger('click')
    expect(wrapper.emitted('change-status')[0]).toEqual([expect.objectContaining({ id: 't1' }), 'blocked'])
  })

  it('emits the chosen priority from the priority icon', async () => {
    const wrapper = mount(TaskCard, { props: { task: task() }, ...stub })
    const select = wrapper.get('.task-priority-select')
    expect(select.get('.task-priority').classes()).toContain('prio-urgent')
    await select.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((option) => option.text().includes('Low'))
      .trigger('click')
    expect(wrapper.emitted('change-priority')[0]).toEqual([expect.objectContaining({ id: 't1' }), 0])
  })

  it('emits toggle from the select checkbox when selectable', async () => {
    const wrapper = mount(TaskCard, {
      props: { task: task(), selectable: true, selected: true },
      ...stub
    })
    expect(wrapper.classes()).toContain('select-item')
    await wrapper.get('.row-check').trigger('change')
    expect(wrapper.emitted('toggle')).toEqual([['t1']])
  })

  it('renders linked people and filters on click', async () => {
    const wrapper = mount(TaskCard, {
      props: { task: task({ person_ids: ['p1'] }), people: [{ id: 'p1', name: 'Ada' }] },
      ...stub
    })
    const chip = wrapper.get('.person-chip')
    expect(chip.text()).toBe('Ada')
    await chip.trigger('click')
    expect(store.personFilter).toBe('p1')
  })

  it('shows the deadline state and hides the picker for the deadlines list', () => {
    const soon = new Date(Date.now() + 3_600_000).toISOString()
    const wrapper = mount(TaskCard, {
      props: { task: task({ deadline: soon }), showStatus: false, showPriority: false, showDeadlineTime: true },
      ...stub
    })
    expect(wrapper.find('.task-status-select').exists()).toBe(false)
    expect(wrapper.get('.badge.warn').text()).toBe('Due today')
    expect(wrapper.text()).toContain(new Date(soon).toLocaleString(undefined, { month: 'short', day: 'numeric' }))
  })
})

describe('TaskLink', () => {
  it('renders a task as a status icon and title linking to the task', () => {
    const wrapper = mount(TaskLink, {
      props: { task: { id: 't1', title: 'Task One', status: 'blocked' } },
      ...stub
    })
    expect(wrapper.get('a').attributes('href')).toBe('/task/t1')
    expect(wrapper.get('.task-status.st-blocked').exists()).toBe(true)
    expect(wrapper.text()).toContain('Task One')
  })
})

describe('ItemLink', () => {
  it('renders a source badge and title linking to the item view', () => {
    const wrapper = mount(ItemLink, {
      props: { item: { id: 'i1', source: 'note', title: 'A note' } },
      ...stub
    })
    expect(wrapper.get('a').attributes('href')).toBe('/items/i1')
    expect(wrapper.get('.chip-source').text()).toBe('Note')
    expect(wrapper.text()).toContain('A note')
  })

  it('shows a GitHub item state', () => {
    const wrapper = mount(ItemLink, {
      props: { item: { id: 'i1', source: 'github', title: 'Issue', metadata_json: { state: 'MERGED' } } },
      ...stub
    })
    expect(wrapper.get('.badge.st-merged').text()).toBe('Merged')
    expect(wrapper.find('.chip-source').exists()).toBe(false)
  })

  it('shows a speech emoji for a Slack item', () => {
    const wrapper = mount(ItemLink, {
      props: { item: { id: 'i1', source: 'slack', title: 'Thread' } },
      ...stub
    })
    expect(wrapper.get('.item-emoji').text()).toBe('💬')
    expect(wrapper.find('.chip-source').exists()).toBe(false)
  })

  it('falls back to the url when the item has no title', () => {
    const wrapper = mount(ItemLink, {
      props: { item: { id: 'i1', source: 'url', url: 'https://x' } },
      ...stub
    })
    expect(wrapper.text()).toContain('https://x')
  })

  it('hides the source badge when a group heading names it', () => {
    const wrapper = mount(ItemLink, {
      props: { item: { id: 'i1', source: 'note', title: 'A note' }, showSource: false },
      ...stub
    })
    expect(wrapper.find('.chip-source').exists()).toBe(false)
    expect(wrapper.text()).toContain('A note')
  })
})
