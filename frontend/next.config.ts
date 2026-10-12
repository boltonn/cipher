import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `forbidden()` / `unauthorized()` (+ forbidden.tsx / unauthorized.tsx) for API 403 / 401 reads.
  experimental: { authInterrupts: true },
  images: {
    remotePatterns:
      process.env.NODE_ENV === "development"
        ? [
            {
              protocol: "http",
              hostname: "localhost",
              port: "8000", // your FastAPI port
              pathname: "/api/**",
            },
          ]
        : [],
  },
};

export default nextConfig;
