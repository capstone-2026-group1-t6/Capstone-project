import { Link, NavLink, Outlet } from "react-router-dom"
import { Sparkles } from "lucide-react"

const navItems = [
  { to: "/", label: "Overview" },
  { to: "/upload", label: "Upload Documents" },
  { to: "/chat", label: "Ask AI" },
]
// 
export default function SiteLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* ===== HEADER ===== */}
      <header className="sticky top-0 z-50 border-b border-gray-200 bg-pink-50/80 backdrop-blur">
        <div className="container flex h-16 items-center justify-between px-4">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-pink-500 text-white">
              <Sparkles size={18} />
            </span>
            <span className="flex flex-col leading-none">
              <span className="text-sm font-extrabold tracking-tight text-gray-900">
                Multipurpose RAG
              </span>
              <span className="text-[11px] text-gray-600">
                Internal Knowledge Platform
              </span>
            </span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-gray-900 text-white"
                      : "text-gray-700 hover:bg-gray-100 hover:text-gray-900"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-gray-50">
        <div className="container px-4 py-8">
          <div className="flex items-center justify-between">
            
            {/* Copyright */}
            <p className="text-xs text-gray-600">
              © 2026 Multipurpose RAG System. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}