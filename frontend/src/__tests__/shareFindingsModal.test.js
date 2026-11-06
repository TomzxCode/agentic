import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  findings: vi.fn(),
  decide: vi.fn(),
  createTask: vi.fn(),
  createRun: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    reviews: { findings: mocks.findings, decide: mocks.decide },
    tasks: { create: mocks.createTask },
    runs: { create: mocks.createRun }
  }
}))

import ShareFindingsModal from '../components/ShareFindingsModal.vue'
import { store } from '../store'

const finding = (over = {}) => ({
  step: 'review-pr',
  title: 'Fix the thing',
  description: 'It is broken.',
  severity: 'must',
  status: 'open',
  sha: 'abc1234',
  ...over
})

function mountModal(props = {}) {
  return mount(ShareFindingsModal, {
    props: { repository: 'acme/api', number: 42, url: 'https://github.com/acme/api/pull/42', ...props }
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.findings.mockResolvedValue([finding()])
  mocks.decide.mockImplementation(async (repository, number, decisions) =>
    decisions.map((decision) => finding({ title: decision.title, decision: decision.decision }))
  )
  mocks.createTask.mockResolvedValue({ id: 't9', title: 'Imported', status: 'open' })
  mocks.createRun.mockResolvedValue({ id: 'r1', status: 'queued' })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ShareFindingsModal', () => {
  it('reads the PR findings and sends the selected ones to an agent', async () => {
    mocks.findings.mockResolvedValue([
      finding({ title: 'Fix the thing' }),
      finding({ title: 'Tidy the helper', severity: 'may' })
    ])
    const wrapper = mountModal({ taskId: 't1', taskLabel: 'Land the PR' })
    await flushPromises()

    expect(mocks.findings).toHaveBeenCalledWith('acme/api', 42)
    // The may finding is not selected by default; the must one is.
    expect(wrapper.text()).toContain('Fix the thing')
    expect(wrapper.text()).toContain('1 of 2 selected')

    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.createRun).toHaveBeenCalledWith('t1', { prompt: expect.stringContaining('Fix the thing') })
    const prompt = mocks.createRun.mock.calls[0][1].prompt
    expect(prompt).toContain('pull request acme/api#42')
    expect(prompt).not.toContain('Tidy the helper')
    expect(store.toast).toEqual({ message: 'Sent the findings to an agent', isError: false })
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('imports a task when the PR is not linked to one, then enables sending', async () => {
    const wrapper = mountModal({ taskId: null })
    await flushPromises()

    expect(wrapper.text()).toContain('No task is linked')
    expect(wrapper.find('.btn.primary').exists()).toBe(false)

    const importButton = wrapper.findAll('button').find((button) => button.text().includes('Import into a task'))
    await importButton.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({ github_url: 'https://github.com/acme/api/pull/42' })
    expect(wrapper.emitted('imported')[0][0]).toEqual({ id: 't9', title: 'Imported', status: 'open' })
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.createRun).toHaveBeenCalledWith('t9', expect.any(Object))
  })

  it('says so when the PR has no findings', async () => {
    mocks.findings.mockResolvedValue([])
    const wrapper = mountModal({ taskId: 't1' })
    await flushPromises()
    expect(wrapper.text()).toContain('No must/should/may findings')
  })

  it('records the decision on a finding when the reviewer unchecks it', async () => {
    mocks.findings.mockResolvedValue([
      finding({ title: 'Fix the thing' }),
      finding({ title: 'Tidy the helper', severity: 'may' })
    ])
    const wrapper = mountModal({ taskId: 't1' })
    await flushPromises()

    // The must finding starts checked; unchecking records the skip.
    await wrapper.findAll('input[type=checkbox]')[0].trigger('change')
    await flushPromises()

    expect(mocks.decide).toHaveBeenCalledWith('acme/api', 42, [
      { step: 'review-pr', title: 'Fix the thing', decision: 'skip' }
    ])
  })

  it('records include decisions for every finding on select all', async () => {
    mocks.findings.mockResolvedValue([
      finding({ title: 'Fix the thing' }),
      finding({ title: 'Tidy the helper', severity: 'may' })
    ])
    const wrapper = mountModal({ taskId: 't1' })
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Select all')
      .trigger('click')
    await flushPromises()

    expect(mocks.decide).toHaveBeenCalledWith('acme/api', 42, [
      { step: 'review-pr', title: 'Fix the thing', decision: 'include' },
      { step: 'review-pr', title: 'Tidy the helper', decision: 'include' }
    ])
  })

  it('filters the list without changing the selection or what is sent', async () => {
    mocks.findings.mockResolvedValue([
      finding({ title: 'Fix the thing', step: 'review-pr' }),
      finding({ title: 'Cover the branch', step: 'analyze-test-coverage', severity: 'should' })
    ])
    const wrapper = mountModal({ taskId: 't1' })
    await flushPromises()
    expect(wrapper.text()).toContain('2 of 2 selected')

    const sourceButton = (label) =>
      wrapper.findAll('.share-sources button').find((button) => button.text().includes(label))

    const listedTitles = () => wrapper.findAll('.share-finding-title').map((node) => node.text())

    await sourceButton('Coverage').trigger('click')
    await flushPromises()

    // Hiding a source changes the view only: no decision is written and the
    // hidden finding stays selected.
    expect(mocks.decide).not.toHaveBeenCalled()
    expect(listedTitles()).toEqual(['Fix the thing'])
    expect(wrapper.text()).toContain('2 of 2 selected')

    // The hidden finding is still sent.
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    const prompt = mocks.createRun.mock.calls[0][1].prompt
    expect(prompt).toContain('Fix the thing')
    expect(prompt).toContain('Cover the branch')

    // Re-enabling the source restores its finding and its selection.
    await sourceButton('All').trigger('click')
    await flushPromises()
    expect(listedTitles()).toEqual(['Fix the thing', 'Cover the branch'])
    expect(wrapper.text()).toContain('2 of 2 selected')

    // None hides every source; the selection and the send action stay intact.
    await sourceButton('None').trigger('click')
    await flushPromises()
    expect(listedTitles()).toEqual([])
    expect(wrapper.text()).toContain('No findings from the selected sources.')
    expect(wrapper.text()).toContain('The 2 selected from hidden sources stay selected.')
    expect(wrapper.text()).toContain('2 of 2 selected')
    expect(wrapper.get('.btn.primary').attributes('disabled')).toBeUndefined()

    await sourceButton('All').trigger('click')
    await flushPromises()
    expect(listedTitles()).toEqual(['Fix the thing', 'Cover the branch'])
    expect(wrapper.text()).toContain('2 of 2 selected')
  })
})
