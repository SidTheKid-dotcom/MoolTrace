import type { NextConfig } from "next";

const apiOrigin = (process.env.MOOLTRACE_API_ORIGIN || "http://127.0.0.1:4317").replace(
  /\/$/,
  "",
);

const nextConfig: NextConfig = {
  cacheComponents: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  agentRules: false,
  devIndicators: false,
  experimental: {
    proxyTimeout: 130_000,
  },
  async rewrites() {
    return [
      {
        source: "/nw/:path*",
        destination: `${apiOrigin}/:path*`,
      },
      {
        source: "/mcp",
        destination: `${apiOrigin}/mcp`,
      },
      {
        source: "/mcp/:path*",
        destination: `${apiOrigin}/mcp/:path*`,
      },
    ];
  },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
