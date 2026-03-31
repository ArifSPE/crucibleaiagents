import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { AuditPage } from "../pages/AuditPage";
import { DaemonsPage } from "../pages/DaemonsPage";
import { ProvidersPage } from "../pages/ProvidersPage";
import { WatcherPage } from "../pages/WatcherPage";
import { ChatPage } from "../pages/ChatPage";

const PackagesPage = lazy(async () => {
  const module = await import("../pages/PackagesPage");
  return { default: module.PackagesPage };
});

const ChatMemoryPage = lazy(async () => {
  const module = await import("../pages/ChatMemoryPage");
  return { default: module.ChatMemoryPage };
});

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route
          path="/chat-memory"
          element={(
            <Suspense fallback={<div className="page-state">Loading memory console…</div>}>
              <ChatMemoryPage />
            </Suspense>
          )}
        />
        <Route
          path="/packages"
          element={(
            <Suspense fallback={<div className="page-state">Loading packages console...</div>}>
              <PackagesPage />
            </Suspense>
          )}
        />
        <Route path="/watcher" element={<WatcherPage />} />
        <Route path="/daemons" element={<DaemonsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}