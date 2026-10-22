/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        night: '#060A18',          // page background
        panel: '#0C1326',          // cards and surfaces
        panel2: '#111A33',         // raised or inset surfaces
        edge: '#1D2847',           // borders
        fog: '#E7ECFA',            // text
        brand: '#2F6BFF',          // primary actions, skills you have
        'brand-light': '#7FAEFF',  // links, accents on dark
        amber: '#F6B34A',          // skills to build
        mint: '#3DD9B4',           // growth
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        lift: '0 0 0 1px rgba(127,174,255,0.06), 0 24px 48px -28px rgba(0,0,0,0.9)',
        glow: '0 0 0 1px rgba(127,174,255,0.25), 0 18px 50px -18px rgba(47,107,255,0.65)',
      },
    },
  },
  plugins: [],
}
