import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  settingsUpdate: vi.fn(),
  scan: vi.fn(),
  loadRepositories: vi.fn(),
  notify: vi.fn()
}))

vi.mock('../api', () => ({
  api: { settings: { update: mocks.settingsUpdate }, reviews: { scan: mocks.scan } }
}))

vi.mock('../store', () => ({
  store: { repositories: [], notify: mocks.notify, loadRepositories: mocks.loadRepositories },
  timeAgo: () => 'just now'
}))

import SettingsReviewScan from '../components/SettingsReviewScan.vue'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.settingsUpdate.mockResolvedValue({})
  mocks.scan.mockResolvedValue({})
  mocks.loadRepositories.mockResolvedValue()
})

describe('SettingsReviewScan', () => {
  it('saves the review SLO on blur', async () => {
    const wrapper = mount(SettingsReviewScan, {
      props: { overrides: { review_slo: '8h' }, defaults: { review_slo: '' }, active: true }
    })
    await flushPromises()

    const slo = wrapper.get('input[placeholder="1d"]')
    expect(slo.element.value).toBe('8h')

    await slo.setValue('2d')
    await slo.trigger('blur')
    await flushPromises()

    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ review_slo: '2d' })
  })

  it('saves the review nudge SLO on blur', async () => {
    const wrapper = mount(SettingsReviewScan, {
      props: {
        overrides: { review_slo: '', review_nudge_slo: '1h30m' },
        defaults: { review_nudge_slo: '' },
        active: true
      }
    })
    await flushPromises()

    const nudge = wrapper.findAll('input[placeholder="1d"]')[1]
    expect(nudge).toBeTruthy()
    expect(nudge.element.value).toBe('1h30m')

    await nudge.setValue('2h')
    await nudge.trigger('blur')
    await flushPromises()

    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ review_nudge_slo: '2h' })
    expect(wrapper.text()).toContain('Review nudge SLO')
  })
})
