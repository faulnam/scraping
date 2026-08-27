/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: "#0B0F19",
        sidebarActive: "#1E293B",
        contentBg: "#F5F6F8",
        accentBlue: "#1D4ED8",
        accentBlueBg: "#DBEAFE",
        highlightLead: "#ECFDF5",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
}
