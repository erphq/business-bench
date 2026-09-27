import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import { execSync } from "node:child_process";

// Every page is rebuilt from the repository, so a page changes when the repository does: use the last commit's date.
const lastmod = (() => {
  try { return execSync("git log -1 --format=%cI", { cwd: new URL(".", import.meta.url) }).toString().trim(); }
  catch { return new Date().toISOString(); }
})();

export default defineConfig({
  site: process.env.SITE_URL || "https://businessbench.org",
  output: "static",
  trailingSlash: "never",
  build: { format: "file" },
  integrations: [sitemap({
    filter: (page) => !/\/404$/.test(page),
    serialize: (item) => ({ ...item, lastmod }),
  })],
  devToolbar: { enabled: false },
  vite: { server: { strictPort: true, fs: { allow: [".."] } } },
});
