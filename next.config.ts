import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // In Docker, BACKEND_URL is http://backend:3000
    // Locally, it's http://localhost:3000
    const backendHost = process.env.BACKEND_URL || "http://backend:3000";

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendHost}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
