import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  routeQuery: {},
  push: vi.fn(),
  peopleCreate: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery }),
  useRouter: () => ({ push: mocks.push })
}))

vi.mock('../api', () => ({
  api: { people: { create: mocks.peopleCreate } }
}))

import PersonCreateView from '../views/PersonCreateView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const mountView = () => mount(PersonCreateView, { global: { stubs: { RouterLink: RouterLinkStub } } })

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.routeQuery = {}
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PersonCreateView', () => {
  it('prefills the name and alias from the handle a listing could not resolve', async () => {
    mocks.routeQuery = { name: 'ghost', alias: 'ghost' }
    const wrapper = mountView()

    expect(wrapper.get('#person-name').element.value).toBe('ghost')
    expect(wrapper.get('#person-aliases').element.value).toBe('ghost')
    expect(wrapper.text()).toContain('No person carries “ghost” yet')
  })

  it('creates the person with its aliases and opens their page', async () => {
    mocks.routeQuery = { name: 'ghost', alias: 'ghost' }
    mocks.peopleCreate.mockResolvedValue({ id: 'p9', name: 'Ghost' })
    const wrapper = mountView()

    await wrapper.get('#person-name').setValue('Ghost Writer')
    await wrapper.get('#person-aliases').setValue('ghost, ghost@example.com, Ghost')
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    expect(mocks.peopleCreate).toHaveBeenCalledWith({
      name: 'Ghost Writer',
      aliases: ['ghost', 'ghost@example.com'],
      notes: ''
    })
    expect(store.loadPeople).toHaveBeenCalled()
    expect(mocks.push).toHaveBeenCalledWith('/person/p9')
  })

  it('will not create a person without a name', async () => {
    const wrapper = mountView()
    expect(wrapper.get('button.primary').attributes('disabled')).toBeDefined()
  })

  it('shows an error and stays on the page when creation fails', async () => {
    mocks.peopleCreate.mockRejectedValue(new Error('name is required'))
    const wrapper = mountView()

    await wrapper.get('#person-name').setValue('Ghost')
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    expect(store.toast).toEqual({ message: 'name is required', isError: true })
    expect(mocks.push).not.toHaveBeenCalled()
  })
})
