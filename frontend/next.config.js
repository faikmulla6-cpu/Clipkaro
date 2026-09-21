const path = require('path');

if (process.env.NODE_ENV === "production" && !process.env.BACKEND_URL) {
  throw new Error("BACKEND_URL is required for the production Hostinger proxy.");
}
const backendUrl = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const browserSecurityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: 'camera=(), microphone=(), geolocation=(), payment=(self "https://*.razorpay.com")' },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  {
    key: "Content-Security-Policy",
    value: "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self' https://*.razorpay.com; img-src 'self' data: blob: https://storage.googleapis.com https://*.razorpay.com; media-src 'self' blob: https://storage.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self' 'unsafe-inline' https://checkout.razorpay.com https://*.razorpay.com; connect-src 'self' https://storage.googleapis.com https://*.razorpay.com wss://*.razorpay.com; frame-src https://*.razorpay.com; worker-src 'self' blob:; manifest-src 'self'; upgrade-insecure-requests",
  },
];

const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "yt3.ggpht.com" },
      { protocol: "https", hostname: "i.ytimg.com" },
    ],
  },
  turbopack: {
    root: path.join(__dirname),
  },
  experimental: {
    proxyClientMaxBodySize: "500mb",
  },
  async headers() {
    return [{ source: "/:path*", headers: browserSecurityHeaders }];
  },
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "www.clipkaro.pro" }],
        destination: "https://clipkaro.pro/:path*",
        permanent: true,
      },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

module.exports = nextConfig;
