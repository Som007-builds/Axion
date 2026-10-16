import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

const eslintConfig = [
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This dashboard deliberately hydrates from localStorage and adopts
      // externally-supplied props inside effects. That is a legitimate
      // "sync to external system" pattern (https://react.dev/learn/you-might-not-need-an-effect),
      // so treat the React-Compiler perf advisory as a warning, not a CI failure.
      'react-hooks/set-state-in-effect': 'warn',
      // Allow intentionally-unused identifiers prefixed with `_`
      // (e.g. the `node` argument react-markdown passes to custom renderers).
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    ignores: ['.next/**', 'out/**', 'build/**', 'next-env.d.ts', 'lint-output.txt'],
  },
]

export default eslintConfig
