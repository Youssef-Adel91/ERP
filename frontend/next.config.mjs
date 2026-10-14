/** @type {import('next').NextConfig} */
const nextConfig = {
  // Suppress the "N" dev overlay badge (was in root next.config.ts)
  devIndicators: false,

  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
