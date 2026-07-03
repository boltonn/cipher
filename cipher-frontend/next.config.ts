import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
