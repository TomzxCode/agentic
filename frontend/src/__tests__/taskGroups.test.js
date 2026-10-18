import { describe, expect, it } from 'vitest'
import { TASK_GROUPINGS, groupTasks } from '../taskGroups'

const task = (over) => ({ id: over.id, status: 'open', priority: 2, ...over })

describe('groupTasks', () => {
  it('lists the grouping choices with None leading', () => {
    expect(TASK_GROUPINGS[0]).toEqual({ value: '', label: 'None' })
    expect(TASK_GROUPINGS.map((g) => g.value)).toEqual(['', 'status', 'priority', 'person', 'tag', 'repository'])
  })

  it('returns one unlabeled section when no grouping is set', () => {
    const tasks = [task({ id: 't1' }), task({ id: 't2' })]
    const groups = groupTasks(tasks, '')
    expect(groups).toHaveLength(1)
    expect(groups[0]).toMatchObject({ key: '', label: null })
    expect(groups[0].tasks.map((t) => t.id)).toEqual(['t1', 't2'])
  })

  it('groups by status in status order, keeping only the groups in use', () => {
    const tasks = [
      task({ id: 't1', status: 'done' }),
      task({ id: 't2', status: 'blocked' }),
      task({ id: 't3', status: 'open' }),
      task({ id: 't4', status: 'blocked' })
    ]
    const groups = groupTasks(tasks, 'status')
    expect(groups.map((g) => g.label)).toEqual(['Open', 'Blocked', 'Done'])
    expect(groups[1].tasks.map((t) => t.id)).toEqual(['t2', 't4'])
  })

  it('groups by priority most urgent first, defaulting a missing priority to high', () => {
    const tasks = [task({ id: 't1', priority: 0 }), task({ id: 't2', priority: 3 }), { id: 't3', status: 'open' }]
    const groups = groupTasks(tasks, 'priority')
    expect(groups.map((g) => g.label)).toEqual(['Urgent', 'High', 'Low'])
    expect(groups[1].tasks.map((t) => t.id)).toEqual(['t3'])
  })

  it('puts a task under each linked person and collects the unlinked ones', () => {
    const people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    const tasks = [
      task({ id: 't1', person_ids: ['p1', 'p2'] }),
      task({ id: 't2', person_ids: [] }),
      task({ id: 't3', person_ids: ['p2'] })
    ]
    const groups = groupTasks(tasks, 'person', { people })
    expect(groups.map((g) => g.label)).toEqual(['Ada', 'Grace', 'No person'])
    expect(groups[0].tasks.map((t) => t.id)).toEqual(['t1'])
    expect(groups[1].tasks.map((t) => t.id)).toEqual(['t1', 't3'])
    expect(groups[2].tasks.map((t) => t.id)).toEqual(['t2'])
  })

  it('groups by tag, with untagged tasks last', () => {
    const tasks = [task({ id: 't1', tags: ['ui', 'bug'] }), task({ id: 't2', tags: [] })]
    const groups = groupTasks(tasks, 'tag')
    expect(groups.map((g) => g.label)).toEqual(['bug', 'ui', 'No tags'])
    expect(groups[0].tasks.map((t) => t.id)).toEqual(['t1'])
  })

  it('groups by the first repository linked to the task (the main repository)', () => {
    const repositories = [
      { id: 'r1', name: 'alpha' },
      { id: 'r2', name: 'beta' }
    ]
    const tasks = [
      task({ id: 't1', repository_ids: ['r2', 'r1'] }),
      task({ id: 't2', repository_ids: ['r1'] }),
      task({ id: 't3', repository_ids: [] }),
      task({ id: 't4', repository_ids: ['missing'] })
    ]
    const groups = groupTasks(tasks, 'repository', { repositories })
    expect(groups.map((g) => g.label)).toEqual(['alpha', 'beta', 'No repository'])
    // t1 leads with r2, so it lands under beta, not alpha.
    expect(groups[0].tasks.map((t) => t.id)).toEqual(['t2'])
    expect(groups[1].tasks.map((t) => t.id)).toEqual(['t1'])
    expect(groups[2].tasks.map((t) => t.id)).toEqual(['t3', 't4'])
  })
})
