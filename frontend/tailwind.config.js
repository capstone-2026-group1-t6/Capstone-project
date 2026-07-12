/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors:{
        "dark": "#1A1A1A",
        "brand-pink": "#ec4899",
        "brand-pink100": "#fbcfe8",
        "brand-blue": "#3b82f6",
      },
    },
  },
  plugins: [],
}