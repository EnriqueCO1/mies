import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a minimal self-contained Node server at `.next/standalone`
  // so the production Docker image stays small (~200 MB instead of
  // ~1 GB with full node_modules). The image's final stage only
  // needs to COPY `.next/standalone`, `.next/static`, and `public`
  // and run `node server.js`.
  //
  // Verified against frontend/node_modules/next/dist/docs/01-app/
  // 03-api-reference/05-config/01-next-config-js/output.md — still
  // the canonical pattern on Next 16.
  output: "standalone",

  reactStrictMode: true,
};

export default nextConfig;
