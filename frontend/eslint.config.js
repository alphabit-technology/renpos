import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        ...globals.browser,
        // provided by Frappe Desk
        frappe: 'readonly', __: 'readonly', $: 'readonly', locals: 'readonly',
        cur_frm: 'readonly', MetaForm: 'readonly', RM: 'readonly',
        __RM_BUILD__: 'readonly',
      },
    },
    ...js.configs.recommended,
    ...reactHooks.configs.flat.recommended,
    plugins: { ...reactHooks.configs.flat.recommended.plugins, 'react-refresh': reactRefresh },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.flat.recommended.rules,
      'no-unused-vars': ['warn', { varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^_' }],
      'react-refresh/only-export-components': 'off',
    },
  },
]
