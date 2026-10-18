import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

import GridColumnChooser from '../components/GridColumnChooser.vue'

enableAutoUnmount(afterEach)

// A stand-in for the AG Grid api the component reads and drives: the columns it
// reports, and a record of every visibility change it was asked to make.
function fakeApi(columns) {
  return {
    getColumns: () =>
      columns.map((column) => ({
        getColId: () => column.colId,
        getColDef: () => ({ headerName: column.label, lockVisible: column.locked }),
        isVisible: () => column.visible
      })),
    setColumnsVisible: vi.fn()
  }
}

const columns = [
  { colId: 'name', label: 'Name', visible: true },
  { colId: 'aliases', label: 'Aliases', visible: true },
  { colId: 'actions', label: 'Actions', visible: true, locked: true }
]

describe('GridColumnChooser', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  const mountChooser = (api, props = {}) => mount(GridColumnChooser, { props: { api, storageKey: 'test', ...props } })

  it('offers a checkbox per column, hiding the locked ones, and no menu until asked', async () => {
    const wrapper = mountChooser(fakeApi(columns))
    expect(wrapper.find('.col-chooser-menu').exists()).toBe(false)

    await wrapper.get('.col-chooser > .btn').trigger('click')
    const options = wrapper.findAll('.col-chooser-option')
    expect(options.map((option) => option.text())).toEqual(['Name', 'Aliases'])
    expect(options.every((option) => option.get('input').element.checked)).toBe(true)
  })

  it('hides a column and remembers the choice', async () => {
    const api = fakeApi(columns)
    const wrapper = mountChooser(api)
    await wrapper.get('.col-chooser > .btn').trigger('click')

    const option = wrapper.findAll('.col-chooser-option')[1]
    await option.get('input').setValue(false)

    expect(api.setColumnsVisible).toHaveBeenCalledWith(['aliases'], false)
    expect(JSON.parse(localStorage.getItem('agentic.gridColumns.test'))).toEqual({ aliases: false })
    expect(wrapper.get('.col-chooser > .btn').text()).toContain('1 hidden')
  })

  it('applies a stored choice when the grid becomes ready', async () => {
    localStorage.setItem('agentic.gridColumns.test', JSON.stringify({ aliases: false }))
    const api = fakeApi([
      { colId: 'name', label: 'Name', visible: true },
      { colId: 'aliases', label: 'Aliases', visible: false }
    ])
    mountChooser(api)
    await flushPromises()
    expect(api.setColumnsVisible).toHaveBeenCalledWith(['aliases'], false)
  })

  it('shows every column again and clears the stored choice', async () => {
    localStorage.setItem('agentic.gridColumns.test', JSON.stringify({ aliases: false }))
    const api = fakeApi([
      { colId: 'name', label: 'Name', visible: true },
      { colId: 'aliases', label: 'Aliases', visible: false }
    ])
    const wrapper = mountChooser(api)
    await wrapper.get('.col-chooser > .btn').trigger('click')

    await wrapper.get('.col-chooser-reset').trigger('click')

    expect(api.setColumnsVisible).toHaveBeenCalledWith(['aliases'], true)
    expect(localStorage.getItem('agentic.gridColumns.test')).toBe('{}')
  })

  it('renders nothing until the grid reports its columns', () => {
    const wrapper = mountChooser(null)
    expect(wrapper.find('.col-chooser').exists()).toBe(false)
  })

  it('closes the menu on an outside click or Escape', async () => {
    const wrapper = mountChooser(fakeApi(columns), { attachTo: document.body })
    await wrapper.get('.col-chooser > .btn').trigger('click')
    expect(wrapper.find('.col-chooser-menu').exists()).toBe(true)

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('.col-chooser-menu').exists()).toBe(false)

    await wrapper.get('.col-chooser > .btn').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('.col-chooser-menu').exists()).toBe(false)
  })
})
