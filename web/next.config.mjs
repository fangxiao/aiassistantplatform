/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // docker 镜像用 standalone 输出(见 web/Dockerfile)
  async rewrites() {
    // 同源 /api 反代到 API 服务(20261010):公网单域名 agent.ailearning.top
    // 即可完整工作——cookie 同域(OAuth/refresh 免跨域),浏览器端 API_BASE=/api;
    // 容器内经 API_ORIGIN=http://api:8000,本地开发回落 localhost:8000
    const apiOrigin = process.env.API_ORIGIN || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
