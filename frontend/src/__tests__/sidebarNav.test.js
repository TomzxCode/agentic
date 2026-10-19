import { beforeEach, describe, expect, it } from 'vitest'
import {
  SIDEBAR_NAV_ITEMS,
  loadSidebarNav,
  moveNavItem,
  moveNavItemTo,
  normalizeSidebarNav,
  resetSidebarNav,
  setNavHidden,
  sidebarNavColumns,
  sidebarNavCustomized,
  sidebarNavList,
  visibleSidebarNav
} from '../sidebarNav'

const DEFAULT = SIDEBAR_NAV_ITEMS.map((item) => item.id)
const ids = (list) => list.map((item) => item.id)

beforeEach(() => {
  localStorage.clear()
  resetSidebarNav()
})

describe('sidebarNav', () => {
  describe('normalizeSidebarNav', () => {
    it('returns the default order with nothing hidden when nothing is stored', () => {
      expect(normalizeSidebarNav(null)).toEqual({ order: DEFAULT, hidden: [] })
    })

    it('keeps a stored order and appends the items the choice predates', () => {
      const result = normalizeSidebarNav({ order: ['settings', 'tasks'], hidden: ['graph'] })
      expect(result.order.slice(0, 2)).toEqual(['settings', 'tasks'])
      expect(result.order).toContain('inbox')
      expect(result.order.length).toBe(DEFAULT.length)
      expect(result.hidden).toEqual(['graph'])
    })

    it('drops unknown and duplicate ids from the order and the hidden set', () => {
      const result = normalizeSidebarNav({
        order: ['tasks', 'ghost', 'tasks', 'settings'],
        hidden: ['ghost', 'graph', 'graph']
      })
      expect(result.order[0]).toBe('tasks')
      expect(result.order[1]).toBe('settings')
      expect(result.order).not.toContain('ghost')
      expect(result.order.length).toBe(DEFAULT.length)
      expect(result.hidden).toEqual(['graph'])
    })

    it('tolerates a stored value that is not shaped as expected', () => {
      expect(normalizeSidebarNav({ order: 'tasks', hidden: 5 })).toEqual({ order: DEFAULT, hidden: [] })
      expect(normalizeSidebarNav('nope')).toEqual({ order: DEFAULT, hidden: [] })
    })
  })

  describe('loadSidebarNav', () => {
    it('reads the stored order and visibility', () => {
      localStorage.setItem('agentic.sidebarNav', JSON.stringify({ order: ['settings', 'tasks'], hidden: ['inbox'] }))
      loadSidebarNav()
      expect(sidebarNavList.value[0].id).toBe('settings')
      expect(ids(visibleSidebarNav.value)).not.toContain('inbox')
    })

    it('falls back to the defaults on corrupt JSON', () => {
      localStorage.setItem('agentic.sidebarNav', '{not json')
      loadSidebarNav()
      expect(ids(sidebarNavList.value)).toEqual(DEFAULT)
    })
  })

  describe('visibility', () => {
    it('hides and re-shows an item, persisting the choice', () => {
      setNavHidden('graph', true)
      expect(ids(visibleSidebarNav.value)).not.toContain('graph')
      expect(JSON.parse(localStorage.getItem('agentic.sidebarNav')).hidden).toEqual(['graph'])

      setNavHidden('graph', false)
      expect(ids(visibleSidebarNav.value)).toContain('graph')
      expect(JSON.parse(localStorage.getItem('agentic.sidebarNav')).hidden).toEqual([])
    })

    it('ignores an unknown id', () => {
      setNavHidden('ghost', true)
      expect(sidebarNavCustomized.value).toBe(false)
    })
  })

  describe('moveNavItem', () => {
    it('swaps an item with its neighbour', () => {
      moveNavItem('inbox', 1)
      expect(ids(sidebarNavList.value).slice(0, 3)).toEqual(['tasks', 'reviews', 'inbox'])
      moveNavItem('inbox', -1)
      expect(ids(sidebarNavList.value).slice(0, 3)).toEqual(['tasks', 'inbox', 'reviews'])
    })

    it('does nothing at the ends', () => {
      moveNavItem('tasks', -1)
      expect(sidebarNavList.value[0].id).toBe('tasks')
      moveNavItem('settings', 1)
      expect(sidebarNavList.value.at(-1).id).toBe('settings')
    })

    it('moves to an explicit index and clamps to the bounds', () => {
      moveNavItemTo('tasks', 2)
      expect(ids(sidebarNavList.value).slice(0, 3)).toEqual(['inbox', 'reviews', 'tasks'])
      moveNavItemTo('tasks', 99)
      expect(sidebarNavList.value.at(-1).id).toBe('tasks')
      moveNavItemTo('tasks', -5)
      expect(sidebarNavList.value[0].id).toBe('tasks')
    })
  })

  describe('derived values', () => {
    it('sizes the grid to the visible items, six at most', () => {
      expect(sidebarNavColumns.value).toBe(6)
      for (const id of SIDEBAR_NAV_ITEMS.slice(2).map((item) => item.id)) setNavHidden(id, true)
      expect(sidebarNavColumns.value).toBe(2)
      for (const item of SIDEBAR_NAV_ITEMS) setNavHidden(item.id, true)
      expect(sidebarNavColumns.value).toBe(1)
    })

    it('reports whether the choice differs from the default', () => {
      expect(sidebarNavCustomized.value).toBe(false)
      setNavHidden('gantt', true)
      expect(sidebarNavCustomized.value).toBe(true)

      resetSidebarNav()
      expect(sidebarNavCustomized.value).toBe(false)
      expect(JSON.parse(localStorage.getItem('agentic.sidebarNav'))).toEqual({ order: DEFAULT, hidden: [] })

      moveNavItem('inbox', -1)
      expect(sidebarNavCustomized.value).toBe(true)
      resetSidebarNav()
      expect(sidebarNavCustomized.value).toBe(false)
    })
  })
})
