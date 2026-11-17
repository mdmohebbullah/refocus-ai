/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        navy: 'rgb(var(--navy) / <alpha-value>)',
        fact: { DEFAULT: 'rgb(var(--fact) / <alpha-value>)', bg: 'rgb(var(--fact-bg) / <alpha-value>)' },
        guess: { DEFAULT: 'rgb(var(--guess) / <alpha-value>)', bg: 'rgb(var(--guess-bg) / <alpha-value>)' },
        ok: { DEFAULT: 'rgb(var(--ok) / <alpha-value>)', bg: 'rgb(var(--ok-bg) / <alpha-value>)' },
        danger: { DEFAULT: 'rgb(var(--danger) / <alpha-value>)', bg: 'rgb(var(--danger-bg) / <alpha-value>)' },
        excl: 'rgb(var(--excl) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['"Patrick Hand"', '"Comic Sans MS"', 'system-ui', 'sans-serif'],
        serif: ['"Courier Prime"', '"Courier New"', 'monospace'],
        hand: ['Caveat', '"Brush Script MT"', 'cursive'],
      },
      fontSize: { sm: ['15px', '22px'], xs: ['13px', '18px'] },
    },
  },
  plugins: [],
}
