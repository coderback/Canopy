import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained .next/standalone (minimal server.js + traced deps) so
  // the Docker runtime image needs no node_modules install. See Dockerfile.
  output: "standalone",
  // Pin the workspace root — a stray package-lock.json in the home directory
  // otherwise makes Next infer the wrong root (multiple-lockfiles warning).
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
