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

  it('saves the review auto-poke schedule on blur', async () => {
    const wrapper = mount(SettingsReviewScan, {
      props: {
        overrides: { review_auto_poke: '24h,26h,28h' },
        defaults: { review_auto_poke: '' },
        active: true
      }
    })
    await flushPromises()

    const autoPoke = wrapper.get('input[placeholder="24h,26h,28h"]')
    expect(autoPoke.element.value).toBe('24h,26h,28h')

    await autoPoke.setValue('24h+1h')
    await autoPoke.trigger('blur')
    await flushPromises()

    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ review_auto_poke: '24h+1h' })
    expect(wrapper.text()).toContain('Review auto-poke')
  })

  it('saves the auto-poke message on blur', async () => {
    const wrapper = mount(SettingsReviewScan, {
      props: {
        overrides: { review_auto_poke_message: 'Waiting {elapsed}' },
        defaults: { review_auto_poke_message: '' },
        active: true
      }
    })
    await flushPromises()

    const message = wrapper.get('textarea')
    expect(message.element.value).toBe('Waiting {elapsed}')

    await message.setValue('SLO {slo}; waited {elapsed}; {link}')
    await message.trigger('blur')
    await flushPromises()

    expect(mocks.settingsUpdate).toHaveBeenCalledWith({
      review_auto_poke_message: 'SLO {slo}; waited {elapsed}; {link}'
    })
    expect(wrapper.text()).toContain('Auto-poke message')
  })

  it('saves the manual poke message on blur', async () => {
    const wrapper = mount(SettingsReviewScan, {
      props: {
        overrides: { review_poke_message: 'Age {elapsed}' },
        defaults: { review_poke_message: '' },
        active: true
      }
    })
    await flushPromises()

    const message = wrapper.findAll('textarea')[1]
    expect(message.element.value).toBe('Age {elapsed}')

    await message.setValue('SLO {slo}; age {elapsed}; {link}')
    await message.trigger('blur')
    await flushPromises()

    expect(mocks.settingsUpdate).toHaveBeenCalledWith({
      review_poke_message: 'SLO {slo}; age {elapsed}; {link}'
    })
    expect(wrapper.text()).toContain('Poke message')
  })
})
