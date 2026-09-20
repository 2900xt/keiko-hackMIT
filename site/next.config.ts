import type { NextConfig } from "next";

// Static export: the GitHub Pages workflow uploads `out/`. The detection
// database stays at site/data/ (its raw-GitHub URL is public API);
// the dev and build scripts copy it into public/data (gitignored) so the export ships it.
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
