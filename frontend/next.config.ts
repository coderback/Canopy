import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root — a stray package-lock.json in the home directory
  // otherwise makes Next infer the wrong root (multiple-lockfiles warning).
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
