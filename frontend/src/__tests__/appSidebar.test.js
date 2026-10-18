import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksCreate: vi.fn(),
  githubIssues: vi.fn(),
  githubIssue: vi.fn()
}))

const route = reactive({ fullPath: '/', name: 'tasks', params: {}, query: {} })

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: mocks.push })
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.tasksUpdate, create: mocks.tasksCreate },
    github: { issues: mocks.githubIssues, issue: mocks.githubIssue }
  }
}))

import App from '../App.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }
const SearchSelectStub = {
  props: ['modelValue', 'options', 'placeholder', 'sort', 'variant'],
  emits: ['update:modelValue'],
  template:
    '<div class="ss"><button v-for="o in options" :key="o.value" class="ss-opt" @click="$emit(\'update:modelValue\', o.value)">{{ o.label }}</button></div>'
}
const passthrough = { template: '<div><slot /></div>' }

const stubs = {
  RouterLink: RouterLinkStub,
  RouterView: true,
  SearchSelect: SearchSelectStub,
  RepositorySelect: passthrough,
  StatusIcon: true,
  PriorityIcon: true,
  CommandPalette: { props: ['items'], emits: ['select', 'close'], template: '<div class="palette-stub"></div>' }
}

function mountApp() {
  return mount(App, { attachTo: document.body, global: { stubs } })
}

// Same App, but with the real command palette so its items can be inspected.
function mountAppWithPalette() {
  const withoutPalette = { ...stubs }
  delete withoutPalette.CommandPalette
  return mount(App, { attachTo: document.body, global: { stubs: withoutPalette } })
}

beforeEach(() => {
  vi.clearAllMocks()
  route.fullPath = '/'
  route.name = 'tasks'
  route.params = {}
  store.tasks = []
  store.tags = []
  store.people = []
  store.items = []
  store.tagFilter = ''
  store.repositories = []
  store.groups = []
  store.settings = {}
  store.hintMode = false
  store.toast = null
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadTags').mockResolvedValue()
  vi.spyOn(store, 'loadGroups').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadItems').mockResolvedValue()
  vi.spyOn(store, 'loadSettings').mockResolvedValue()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('App', () => {
  describe('sidebar swipe', () => {
    // The drawer only exists below the 760px breakpoint.
    beforeEach(() => {
      window.innerWidth = 375
    })
    afterEach(() => {
      window.innerWidth = 1024
    })

    // jsdom has no TouchEvent, so build a plain event carrying the touches the
    // handler reads.
    function touch(type, x, y) {
      const event = new Event(type, { bubbles: true, cancelable: true })
      const point = { clientX: x, clientY: y }
      event.touches = type === 'touchend' || type === 'touchcancel' ? [] : [point]
      event.changedTouches = [point]
      return event
    }
    const start = (x, y = 300, el = document.body) => el.dispatchEvent(touch('touchstart', x, y))
    const move = (x, y = 300, el = document.body) => el.dispatchEvent(touch('touchmove', x, y))
    const end = (x, y = 300, el = document.body) => el.dispatchEvent(touch('touchend', x, y))

    it('opens the drawer on a rightward swipe', async () => {
      const wrapper = mountApp()
      await flushPromises()
      start(200)
      move(230)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-dragging')
      move(330)
      end(330)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-open')
    })

    it('opens from a swipe that starts at the screen edge', async () => {
      const wrapper = mountApp()
      await flushPromises()
      start(2)
      move(60)
      move(320)
      end(320)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-open')
    })

    it('opens the drawer on a quick flick, short of half the screen', async () => {
      const wrapper = mountApp()
      await flushPromises()
      start(200)
      move(240)
      end(240)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-open')
    })

    it('opens after an early sideways drift', async () => {
      const wrapper = mountApp()
      await flushPromises()
      start(200, 300)
      move(212, 340)
      move(330, 340)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-dragging')
      end(330, 340)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-open')
    })

    it('leaves a sideways-scrolling strip alone', async () => {
      const wrapper = mountApp()
      await flushPromises()
      const strip = document.createElement('div')
      Object.defineProperty(strip, 'clientWidth', { value: 300 })
      Object.defineProperty(strip, 'scrollWidth', { value: 900 })
      wrapper.get('.main').element.appendChild(strip)
      start(200, 300, strip)
      move(340, 300, strip)
      end(340, 300, strip)
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
    })

    it('ignores a vertical drag', async () => {
      const wrapper = mountApp()
      await flushPromises()
      start(200, 100)
      move(220, 500)
      end(220, 500)
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
    })

    it('does not open the drawer while a modal is open', async () => {
      const wrapper = mountApp()
      await flushPromises()
      await wrapper.get('.new-task').trigger('click')
      start(10)
      move(320)
      end(320)
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
    })

    it('closes the drawer on a leftward swipe', async () => {
      const wrapper = mountApp()
      await flushPromises()
      await wrapper.get('.menu-btn').trigger('click')
      start(320)
      move(180)
      move(40)
      end(40)
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
    })

    it('springs back on a swipe too short to commit', async () => {
      const wrapper = mountApp()
      await flushPromises()
      await wrapper.get('.menu-btn').trigger('click')
      start(320)
      move(300)
      end(300)
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-open')
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-dragging')
    })
  })

  describe('sidebar resize', () => {
    // The handle only exists on the desktop layout.
    beforeEach(() => {
      localStorage.clear()
    })

    function pointer(type, x) {
      const event = new Event(type, { bubbles: true, cancelable: true })
      event.clientX = x
      event.button = 0
      return event
    }
    const appWidth = (wrapper) => wrapper.get('.app').element.style.getPropertyValue('--sidebar-width')

    async function drag(wrapper, from, to) {
      wrapper.get('.sidebar-resizer').element.dispatchEvent(pointer('pointerdown', from))
      await nextTick()
      window.dispatchEvent(pointer('pointermove', to))
      await nextTick()
      window.dispatchEvent(pointer('pointerup', to))
      await nextTick()
    }

    it('starts at the default width and drags with the handle', async () => {
      const wrapper = mountApp()
      await flushPromises()
      expect(appWidth(wrapper)).toBe('300px')

      const handle = wrapper.get('.sidebar-resizer')
      handle.element.dispatchEvent(pointer('pointerdown', 500))
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-resizing')

      window.dispatchEvent(pointer('pointermove', 560))
      await nextTick()
      expect(appWidth(wrapper)).toBe('360px')

      window.dispatchEvent(pointer('pointerup', 560))
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-resizing')
      expect(localStorage.getItem('agentic.sidebarWidth')).toBe('360')
    })

    it('clamps the drag to the minimum and maximum width', async () => {
      const wrapper = mountApp()
      await flushPromises()
      await drag(wrapper, 500, 50)
      expect(appWidth(wrapper)).toBe('260px')
      await drag(wrapper, 500, 2000)
      expect(appWidth(wrapper)).toBe('560px')
    })

    it('sizes with the keyboard from the separator', async () => {
      const wrapper = mountApp()
      await flushPromises()
      const handle = wrapper.get('.sidebar-resizer')
      await handle.trigger('keydown', { key: 'ArrowRight' })
      expect(appWidth(wrapper)).toBe('310px')
      await handle.trigger('keydown', { key: 'ArrowLeft', shiftKey: true })
      expect(appWidth(wrapper)).toBe('270px')
      await handle.trigger('keydown', { key: 'Home' })
      expect(appWidth(wrapper)).toBe('260px')
      await handle.trigger('keydown', { key: 'End' })
      expect(appWidth(wrapper)).toBe('560px')
      await handle.trigger('keydown', { key: 'Enter' })
      expect(appWidth(wrapper)).toBe('300px')
    })

    it('restores the default width on double-click', async () => {
      const wrapper = mountApp()
      await flushPromises()
      await drag(wrapper, 500, 640)
      expect(appWidth(wrapper)).toBe('440px')
      await wrapper.get('.sidebar-resizer').trigger('dblclick')
      expect(appWidth(wrapper)).toBe('300px')
      expect(localStorage.getItem('agentic.sidebarWidth')).toBe('300')
    })

    it('restores a stored width on mount', async () => {
      localStorage.setItem('agentic.sidebarWidth', '420')
      const wrapper = mountApp()
      await flushPromises()
      expect(appWidth(wrapper)).toBe('420px')
    })

    it('clamps a stored width into the allowed range', async () => {
      localStorage.setItem('agentic.sidebarWidth', '5')
      const wrapper = mountApp()
      await flushPromises()
      expect(appWidth(wrapper)).toBe('260px')
    })

    it('falls back to the default when nothing usable is stored', async () => {
      localStorage.setItem('agentic.sidebarWidth', 'not-a-number')
      const wrapper = mountApp()
      await flushPromises()
      expect(appWidth(wrapper)).toBe('300px')
    })

    it('does not resize on the mobile layout', async () => {
      window.innerWidth = 375
      const wrapper = mountApp()
      await flushPromises()
      wrapper.get('.sidebar-resizer').element.dispatchEvent(pointer('pointerdown', 500))
      window.dispatchEvent(pointer('pointermove', 560))
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-resizing')
      expect(appWidth(wrapper)).toBe('300px')
      window.innerWidth = 1024
    })
  })

  describe('sidebar visibility', () => {
    beforeEach(() => {
      localStorage.clear()
      window.innerWidth = 1024
    })

    it('hides the sidebar from the toggle beside the title and remembers it', async () => {
      const wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-hidden')

      await wrapper.get('.menu-btn').trigger('click')
      expect(wrapper.get('.app').classes()).toContain('sidebar-hidden')
      expect(localStorage.getItem('agentic.sidebarHidden')).toBe('1')
      expect(wrapper.get('.menu-btn').attributes('aria-expanded')).toBe('false')
    })

    it('toggles with Cmd/Ctrl+B', async () => {
      const wrapper = mountApp()
      await flushPromises()

      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', metaKey: true, cancelable: true }))
      await nextTick()
      expect(wrapper.get('.app').classes()).toContain('sidebar-hidden')

      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, cancelable: true }))
      await nextTick()
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-hidden')
      expect(localStorage.getItem('agentic.sidebarHidden')).toBe('0')
    })

    it('keeps the toggle in the page flow beside the title', async () => {
      const wrapper = mountApp()
      await flushPromises()
      // Inside .main, ahead of the view, so it floats on the title's line.
      expect(wrapper.get('.main > .menu-btn').exists()).toBe(true)
      expect(wrapper.find('.app > .menu-btn').exists()).toBe(false)
    })

    it('leaves the toggle out of focus hints', async () => {
      const wrapper = mountApp()
      await flushPromises()
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f' }))
      await nextTick()
      expect(store.hintMode).toBe(false)
      expect(wrapper.find('.hint-badge').exists()).toBe(false)
    })

    it('reveals a hidden sidebar from the menu button', async () => {
      localStorage.setItem('agentic.sidebarHidden', '1')
      const wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.app').classes()).toContain('sidebar-hidden')

      await wrapper.get('.menu-btn').trigger('click')
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-hidden')
    })

    it('offers to hide the sidebar from the command palette', async () => {
      const wrapper = mountAppWithPalette()
      await flushPromises()

      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
      await nextTick()
      const item = wrapper.findAll('.palette-item').find((i) => i.text().includes('Hide task list'))
      expect(item).toBeTruthy()
      await item.trigger('click')
      expect(wrapper.get('.app').classes()).toContain('sidebar-hidden')
    })

    it('keeps a mobile drawer close out of the desktop preference', async () => {
      window.innerWidth = 375
      const wrapper = mountApp()
      await flushPromises()

      await wrapper.get('.sidebar-close').trigger('click')
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
      expect(wrapper.get('.app').classes()).not.toContain('sidebar-hidden')
      expect(localStorage.getItem('agentic.sidebarHidden')).toBeNull()
      window.innerWidth = 1024
    })
  })
})
