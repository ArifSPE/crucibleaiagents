import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { AuditPage } from "../pages/AuditPage";
import { DaemonsPage } from "../pages/DaemonsPage";
import { ProvidersPage } from "../pages/ProvidersPage";
import { WatcherPage } from "../pages/WatcherPage";

const PackagesPage = lazy(async () => {
  const module = await import("../pages/PackagesPage");
  return { default: module.PackagesPage };
});

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
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