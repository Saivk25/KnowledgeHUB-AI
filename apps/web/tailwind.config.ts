import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0F172A",
        indigo: "#4F46E5",
        sky: "#0EA5E9",
        emerald: "#10B981",
        amber: "#F59E0B",
        rose: "#E11D48",
        canvas: "#F8FAFC",
        surface: "#FFFFFF",
        edge: "#E2E8F0",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
