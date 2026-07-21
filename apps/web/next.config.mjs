/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output traces exactly the production dependencies each page
  // needs into .next/standalone, so the runtime Docker image doesn't need
  // the full node_modules (devDependencies like typescript/tailwind/postcss
  // included) copied into it -- see apps/web/Dockerfile.
  output: "standalone",
};

export default nextConfig;
