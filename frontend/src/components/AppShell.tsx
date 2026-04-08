import type { PropsWithChildren } from "react";
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { getApiBaseUrl } from "../services/apiClient";

function NavIcon({ path }: { path: string }) {
  return (
    <svg aria-hidden="true" className="nav-links__icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d={path} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", iconPath: "M3 11.5 12 4l9 7.5v8a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { to: "/chat", label: "Chat", iconPath: "M4 6h16v9H8l-4 4z M8 10h8 M8 13h5" },
  { to: "/chat-memory", label: "Chat Memory", iconPath: "M12 8v4l3 3 M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" },
  { to: "/packages", label: "Packages", iconPath: "M4 7.5 12 3l8 4.5-8 4.5z M4 7.5v9L12 21v-9 M20 7.5v9L12 21" },
  { to: "/watcher", label: "Watcher", iconPath: "M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z" },
  { to: "/mcp-server", label: "MCP Server", iconPath: "M4 6h16v12H4z M8 10h8 M8 14h5 M2 9l2 3-2 3 M22 9l-2 3 2 3" },
  { to: "/daemons", label: "Daemons", iconPath: "M4 6h10l6 6v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z M14 6v6h6" },
  { to: "/audit", label: "Audit", iconPath: "M12 3v4 M7 5l3 2 M17 5l-3 2 M5 10h14 M7 21h10 M9 10v7 M15 10v7" },
  { to: "/providers", label: "LLM Providers", iconPath: "M4 7h16 M4 12h16 M4 17h10 M17 17h3 M14 14l3 3-3 3" },
];

export function AppShell({ children }: PropsWithChildren) {
  const [isNavOpen, setIsNavOpen] = useState(true);

  return (
    <div className={`app-shell ${isNavOpen ? "app-shell--nav-open" : "app-shell--nav-closed"}`}>
      <aside className="app-shell__sidebar">
        <div className="sidebar-top-row">
          <button
            aria-label={isNavOpen ? "Collapse navigation" : "Expand navigation"}
            className="nav-toggle nav-toggle--sidebar"
            onClick={() => setIsNavOpen((prev) => !prev)}
            type="button"
            title={isNavOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {isNavOpen ? "<" : ">"}
          </button>
        </div>
        <div className="brand-mark">
          <img alt="CrucibleAgentPlatform logo" className="brand-mark__logo" src="/logo.png" />
          <div>
            <h1>
              <span>CrucibleAgent</span>
              <span>Platform</span>
            </h1>
            <p>Operator Console</p>
          </div>
        </div>
        <nav className="nav-links">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} title={item.label} to={item.to} end={item.to === "/"}>
              <span aria-hidden="true" className="nav-links__icon">
                <NavIcon path={item.iconPath} />
              </span>
              <span className="nav-links__label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <span>Backend API</span>
          <strong>{getApiBaseUrl()}</strong>
        </div>
      </aside>
      <div className="app-shell__main">
        <header className="topbar">
          <div>
            <span className="eyebrow">Secure orchestration</span>
            <h2>Operational control plane</h2>
          </div>
          <p>Monitor packages, trigger runs, inspect logs, and manage provider credentials from one console.</p>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}