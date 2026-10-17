import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ValuesFilter from '../components/ValuesFilter.vue'

// The grid hands the filter its `params`; `api.forEachNode` is how the filter
// reads the rows, so a fake api over a plain array stands in for the grid.
const apiFor = (rows) => ({ forEachNode: (callback) => rows.forEach((data) => callback({ data })) })

const mountFilter = (params) => mount(ValuesFilter, { props: { params } })

describe('ValuesFilter', () => {
  it('lists the distinct values of the column, labelled and sorted', () => {
    const wrapper = mountFilter({
      api: apiFor([{ kind: 'issue' }, { kind: 'pr' }, { kind: 'issue' }]),
      getValues: (data) => [data.kind],
      label: (value) => (value === 'pr' ? 'PR' : 'issue'),
      model: null,
      onModelChange: vi.fn()
    })

    expect(wrapper.findAll('.value-filter-option').map((option) => option.text())).toEqual(['issue', 'PR'])
  })

  it('reports the selected values as a model, and null when nothing is left', async () => {
    const onModelChange = vi.fn()
    const wrapper = mountFilter({
      api: apiFor([{ kind: 'issue' }, { kind: 'pr' }]),
      getValues: (data) => [data.kind],
      model: null,
      onModelChange
    })

    await wrapper.findAll('input[type="checkbox"]')[0].setValue(true)
    expect(onModelChange).toHaveBeenLastCalledWith({ values: ['issue'] })

    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false)
    expect(onModelChange).toHaveBeenLastCalledWith(null)
  })

  it('starts from an existing model', () => {
    const wrapper = mountFilter({
      api: apiFor([{ kind: 'issue' }, { kind: 'pr' }]),
      getValues: (data) => [data.kind],
      model: { values: ['pr'] },
      onModelChange: vi.fn()
    })

    expect(wrapper.findAll('input[type="checkbox"]').map((box) => box.element.checked)).toEqual([false, true])
  })

  it('adds a value box only when the list is long', () => {
    const short = mountFilter({
      api: apiFor([{ author: 'a' }]),
      getValues: (data) => [data.author],
      model: null,
      onModelChange: vi.fn()
    })
    expect(short.find('.value-filter-search').exists()).toBe(false)

    const many = mountFilter({
      api: apiFor(Array.from({ length: 10 }, (_, i) => ({ author: `author-${i}` }))),
      getValues: (data) => [data.author],
      model: null,
      onModelChange: vi.fn()
    })
    expect(many.find('.value-filter-search').exists()).toBe(true)
  })
})
