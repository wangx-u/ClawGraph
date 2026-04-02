import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      boxShadow: {
        panel: "0 14px 48px rgba(7, 12, 24, 0.32)",
        glow: "0 0 0 1px rgba(158, 198, 255, 0.12), 0 18px 60px rgba(34, 73, 140, 0.22)"
      },
      borderRadius: {
        xl2: "1.35rem"
      },
      fontFamily: {
        sans: ["Space Grotesk", "Avenir Next", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "monospace"]
      },
      backgroundImage: {
        "dashboard-grid":
          "linear-gradient(to right, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.04) 1px, transparent 1px)"
      }
    }
  },
  plugins: []
};

export default config;
