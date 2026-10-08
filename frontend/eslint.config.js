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
        cur_frm: 'readonly', MetaForm: 'readonly', REN: 'readonly',
        cur_dialog: 'readonly',
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
      // React Compiler style rules: the code works; fix gradually
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/use-memo': 'warn',
      'no-empty': ['warn', { allowEmptyCatch: true }],
    },
  },
]
