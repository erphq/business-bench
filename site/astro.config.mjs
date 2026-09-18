import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: process.env.SITE_URL || "https://businessbench.org",
  output: "static",
  trailingSlash: "never",
  build: { format: "file" },
  integrations: [sitemap()],
  vite: { server: { strictPort: true, fs: { allow: [".."] } } },
});
