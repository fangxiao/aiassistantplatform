/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // docker 镜像用 standalone 输出(见 web/Dockerfile)
};

export default nextConfig;
