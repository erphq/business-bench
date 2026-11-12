import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: process.env.SITE_URL || "https://businessbench.org",
  output: "static",
  trailingSlash: "never",
  build: { format: "file" },
  integrations: [sitemap({
    filter: (page) => !/\/404\/?$/.test(new URL(page).pathname),
    // Omit lastmod until we can track meaningful changes per page. A repository
    // commit or rebuild date is not a reliable content modification date.
  })],
  devToolbar: { enabled: false },
  vite: { server: { strictPort: true, fs: { allow: [".."] } } },
});
