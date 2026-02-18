import path from "path";
import { fileURLToPath } from "url";

/**
 * Fix __dirname in ES module scope
 */
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,

  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },

    optimizePackageImports: [
      "lucide-react",
      "@radix-ui/react-label",
      "class-variance-authority",
    ],

    // ✅ FIX MOVED HERE
    outputFileTracingRoot: path.join(__dirname, "../../"),
  },

  transpilePackages: [
    "@cursorcode/ui",
    "@cursorcode/db",
    "@cursorcode/types",
  ],

  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "cursorcode.app",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "**.vercel.app",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "images.unsplash.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "api.dicebear.com",
        pathname: "/**",
      },
    ],
    minimumCacheTTL: 60,
    formats: ["image/avif", "image/webp"],
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "X-XSS-Protection",
            value: "1; mode=block",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
        ],
      },
    ];
  },

  output: "standalone",

  async redirects() {
    return [];
  },

  webpack(config, { isServer }) {
    if (!isServer && process.env.ANALYZE === "true") {
      const { BundleAnalyzerPlugin } = require("@next/bundle-analyzer");

      config.plugins.push(
        new BundleAnalyzerPlugin({
          analyzerMode: "static",
          openAnalyzer: false,
          reportFilename: "bundle-analysis.html",
        })
      );
    }

    return config;
  },
};

export default nextConfig;
