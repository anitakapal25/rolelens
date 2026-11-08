import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Read VITE_* variables from the repo-root .env (only VITE_-prefixed vars reach the browser).
  envDir: "..",
  server: { port: 5173 },
});
