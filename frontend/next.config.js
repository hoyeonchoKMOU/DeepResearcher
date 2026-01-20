/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      // beforeFiles rewrites are checked before pages/api routes
      beforeFiles: [],
      // afterFiles rewrites are checked after pages/api routes
      // This allows our API route to handle SSE, then other requests go to backend
      afterFiles: [
        // v3 API routes - Process-based architecture
        {
          source: '/api/research/v3/create',
          destination: 'http://localhost:8000/api/research/v3/create',
        },
        {
          source: '/api/research/v3/:id/status',
          destination: 'http://localhost:8000/api/research/v3/:id/status',
        },
        {
          source: '/api/research/v3/:id/rename',
          destination: 'http://localhost:8000/api/research/v3/:id/rename',
        },
        // Document download routes
        {
          source: '/api/research/v3/:id/documents',
          destination: 'http://localhost:8000/api/research/v3/:id/documents',
        },
        {
          source: '/api/research/v3/:id/documents/:docType/download',
          destination: 'http://localhost:8000/api/research/v3/:id/documents/:docType/download',
        },
        {
          source: '/api/research/v3/:id/documents/:docType/preview',
          destination: 'http://localhost:8000/api/research/v3/:id/documents/:docType/preview',
        },
        // Reset routes
        {
          source: '/api/research/v3/:id/process/research-experiment/reset',
          destination: 'http://localhost:8000/api/research/v3/:id/process/research-experiment/reset',
        },
        {
          source: '/api/research/v3/:id/process/paper-writing/reset',
          destination: 'http://localhost:8000/api/research/v3/:id/process/paper-writing/reset',
        },
        {
          source: '/api/research/v3/:id/process/literature-organization/reset',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-organization/reset',
        },
        // Literature Review specific routes (with hyphens)
        {
          source: '/api/research/v3/:id/process/literature-review/upload',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/upload',
        },
        {
          source: '/api/research/v3/:id/process/literature-review/search',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/search',
        },
        {
          source: '/api/research/v3/:id/process/literature-review/papers/:paperId',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/papers/:paperId',
        },
        {
          source: '/api/research/v3/:id/process/literature-review/papers',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/papers',
        },
        {
          source: '/api/research/v3/:id/process/literature-review/master',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/master',
        },
        {
          source: '/api/research/v3/:id/process/literature-review/process/:paperId',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review/process/:paperId',
        },
        {
          source: '/api/research/v3/:id/process/literature-review',
          destination: 'http://localhost:8000/api/research/v3/:id/process/literature-review',
        },
        // Generic process routes
        {
          source: '/api/research/v3/:id/process/:process/:action*',
          destination: 'http://localhost:8000/api/research/v3/:id/process/:process/:action*',
        },
        {
          source: '/api/research/v3/:id/process/:process',
          destination: 'http://localhost:8000/api/research/v3/:id/process/:process',
        },
        {
          source: '/api/research/v3',
          destination: 'http://localhost:8000/api/research/v3',
        },
        // Legacy API routes
        {
          source: '/api/research/:id/chat',
          destination: 'http://localhost:8000/api/research/:id/chat',
        },
        {
          source: '/api/research/:id/start',
          destination: 'http://localhost:8000/api/research/:id/start',
        },
        {
          source: '/api/research/:id/proceed',
          destination: 'http://localhost:8000/api/research/:id/proceed',
        },
        {
          source: '/api/research/create',
          destination: 'http://localhost:8000/api/research/create',
        },
        {
          source: '/api/research/:id',
          destination: 'http://localhost:8000/api/research/:id',
        },
        {
          source: '/api/research',
          destination: 'http://localhost:8000/api/research',
        },
        {
          source: '/api/auth/:path*',
          destination: 'http://localhost:8000/api/auth/:path*',
        },
      ],
      // fallback is checked after both pages and afterFiles rewrites
      fallback: [],
    };
  },
};

module.exports = nextConfig;
