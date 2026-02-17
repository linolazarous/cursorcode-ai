// packages/config/tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",

  content: [
    // Main Web App
    "../apps/web/app/**/*.{js,ts,jsx,tsx,mdx}",
    "../apps/web/components/**/*.{js,ts,jsx,tsx,mdx}",
    "../apps/web/lib/**/*.{js,ts,jsx,tsx,mdx}",

    // Shared UI Package (if you have one)
    "../packages/ui/**/*.{js,ts,jsx,tsx,mdx}",

    // Any other apps or packages using Tailwind
    // "../apps/admin/**/*.{js,ts,jsx,tsx}",
  ],

  theme: {
    extend: {
      // You can put shared brand colors/fonts here so all apps inherit them
      colors: {
        brand: {
          blue: "#1E88E5",
          glow: "#67E8F9",
          dark: "#0A0A0A",
          card: "#111827",
        },
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },

  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
