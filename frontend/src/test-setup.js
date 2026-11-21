// jsdom lacks DOMMatrixReadOnly too; Vue Flow reads the viewport zoom off the
// transform matrix (m22) after measuring nodes.
if (typeof globalThis.DOMMatrixReadOnly === 'undefined') {
  globalThis.DOMMatrixReadOnly = class DOMMatrixReadOnly {
    constructor(transform = '') {
      const match = /matrix\(([^)]+)\)/.exec(transform)
      const [a = 1, b = 0, c = 0, d = 1] = match ? match[1].split(',').map(Number) : []
      this.m11 = a
      this.m12 = b
      this.m21 = c
      this.m22 = d
    }
  }
}

// jsdom lacks ResizeObserver; Vue Flow (and other layout-aware components) need it.
// A real observer reports the observed element once right after observe(), which is
// how Vue Flow 2.x gets its first node measurement; a silent stub leaves nodes
// unmeasured and their edges unrendered.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    constructor(callback) {
      this.callback = callback
      this.elements = new Set()
    }
    observe(element) {
      this.elements.add(element)
      queueMicrotask(() => this.callback([{ target: element }], this))
    }
    unobserve(element) {
      this.elements.delete(element)
    }
    disconnect() {
      this.elements.clear()
    }
  }
}
