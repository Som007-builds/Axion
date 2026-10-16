/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle for the Docker runtime image.
  output: 'standalone',
  images: {
    unoptimized: true,
  },
}

export default nextConfig
