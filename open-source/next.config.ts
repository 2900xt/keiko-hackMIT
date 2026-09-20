import type { NextConfig } from "next";

// Static export: the GitHub Pages workflow uploads `out/`. The detection
// database stays at open-source/data/ (its raw-GitHub URL is public API);
// `npm run build` copies it into out/data and `public/data` symlinks it for dev.
//
// On a project Pages site the page lives under /<repo>/, so the workflow passes
// that prefix in NEXT_PUBLIC_BASE_PATH (from actions/configure-pages). Locally it
// is unset. Data fetches are relative to the page, so they work either way.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  images: { unoptimized: true },
};

export default nextConfig;
