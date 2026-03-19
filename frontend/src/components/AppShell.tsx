import type { PropsWithChildren } from "react";
import { NavLink } from "react-router-dom";
import { getApiBaseUrl } from "../services/apiClient";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-shell">
      <aside className="app-shell__sidebar">
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
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/packages">Packages</NavLink>
          <NavLink to="/watcher">Watcher</NavLink>
          <NavLink to="/daemons">Daemons</NavLink>
          <NavLink to="/audit">Audit</NavLink>
          <NavLink to="/providers">LLM Providers</NavLink>
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