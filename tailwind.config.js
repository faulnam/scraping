/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/templates/*.html",
    "./app/templates/layouts/*.html",
    "./app/templates/partials/*.html",
    "app/templates/dashboard.html",
    "app/templates/guide.html",
    "app/templates/history.html",
    "app/templates/lead_detail.html",
    "app/templates/leads_list.html",
    "app/templates/login.html",
    "app/templates/settings_api_keys.html",
    "app/templates/settings_profile.html",
    "app/templates/layouts/base.html",
    "app/templates/partials/filter_bar.html",
    "app/templates/partials/leads_table.html",
    "app/templates/partials/metric_card.html",
    "app/templates/partials/nav_sidebar.html",
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
