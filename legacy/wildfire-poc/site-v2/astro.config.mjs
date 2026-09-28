import { defineConfig } from "astro/config";
export default defineConfig({
  output: "static",
  build: { format: "file" },
  site: "https://us-wildfires.netlify.app",
});
