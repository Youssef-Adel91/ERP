import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */

  // Fix HMR WebSocket connection issues on Windows / Arabic paths / proxies
  devIndicators: false,

  webpack(config, { dev, isServer }) {
    if (dev && !isServer) {
      config.watchOptions = {
        poll: 1000,           // poll every 1s instead of using native fs events
        aggregateTimeout: 300,
      };
    }
    return config;
  },
};

export default nextConfig;
