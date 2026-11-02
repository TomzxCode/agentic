import { beforeEach, describe, expect, it } from 'vitest'
import { debugBarVisible, setDebugBarHidden, setDebugBarVisible } from '../debugBar'

beforeEach(() => {
  localStorage.clear()
  setDebugBarVisible(true)
})

describe('debugBar', () => {
  it('shows the bar when nothing has been chosen', () => {
    localStorage.clear()
    expect(debugBarVisible.value).toBe(true)
  })

  it('remembers a hidden bar on the device', () => {
    setDebugBarVisible(false)
    expect(debugBarVisible.value).toBe(false)
    expect(localStorage.getItem('agentic.debugBarHidden')).toBe('1')

    setDebugBarVisible(true)
    expect(debugBarVisible.value).toBe(true)
    expect(localStorage.getItem('agentic.debugBarHidden')).toBe('0')
  })

  it('takes a hidden flag as well as a visible one', () => {
    setDebugBarHidden(true)
    expect(debugBarVisible.value).toBe(false)

    setDebugBarHidden(false)
    expect(debugBarVisible.value).toBe(true)
  })
})
