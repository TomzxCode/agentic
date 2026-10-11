import js from '@eslint/js'
import prettier from 'eslint-config-prettier/flat'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  {
    ignores: ['dist/', 'dev-dist/', 'coverage/', 'node_modules/', '../backend/static/']
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  prettier,
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser }
    },
    rules: {
      'vue/multi-word-component-names': 'off'
    }
  },
  {
    files: ['*.config.js'],
    languageOptions: {
      globals: { ...globals.node }
    }
  },
  {
    files: ['src/**/__tests__/**/*.js', 'src/**/*.{test,spec}.js'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.vitest }
    }
  }
]
