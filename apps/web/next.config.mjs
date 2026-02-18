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


  experimental: {
    serverActions: {
      bodySizeLimit: "10mb"
    }
  },


  transpilePackages: [
    "@cursorcode/ui",
    "@cursorcode/types",
    "@cursorcode/db"
  ],



  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**"
      }
    ]
  },



  webpack: (config) => {

    /**
     * THIS IS THE CRITICAL FIX
     */

    config.resolve.alias["@"] = path.resolve(
      __dirname,
      "../../packages/ui"
    );

    return config;
  }

};


export default nextConfig;
