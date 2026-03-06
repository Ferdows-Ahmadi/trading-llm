import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        slateBlue: "#1B2A41",
        graph: "#02C39A",
        signal: "#F4A261"
      }
    }
  },
  plugins: []
};

export default config;
