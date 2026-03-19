import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { AuditPage } from "../pages/AuditPage";
import { DaemonsPage } from "../pages/DaemonsPage";
import { PackagesPage } from "../pages/PackagesPage";
import { ProvidersPage } from "../pages/ProvidersPage";
import { WatcherPage } from "../pages/WatcherPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/packages" element={<PackagesPage />} />
        <Route path="/watcher" element={<WatcherPage />} />
        <Route path="/daemons" element={<DaemonsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}