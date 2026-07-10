import { Outlet, Link } from 'react-router-dom';

export default function SiteLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <nav className="border-b border-gray-200 bg-white">
        <div className="container flex items-center justify-between px-4 py-4">
          <Link to="/" className="text-xl font-bold text-gray-900">
            RAG System
          </Link>

          <div className="flex items-center gap-6">
            <Link to="/" className="text-sm font-medium text-gray-600 transition hover:text-gray-900">
              Home
            </Link>
            <Link to="/upload" className="text-sm font-medium text-gray-600 transition hover:text-gray-900">
              Upload
            </Link>
            <Link to="/chat" className="text-sm font-medium text-gray-600 transition hover:text-gray-900">
              Chat
            </Link>
          </div>
        </div>
      </nav>

      <main className="flex flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-gray-200 bg-gray-50">
        <div className="container px-4 py-8 text-center">
          <p className="text-sm text-gray-600">
            © 2024 RAG System. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
