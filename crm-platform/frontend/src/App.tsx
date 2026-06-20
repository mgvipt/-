import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Leads from "./pages/Leads";
import Deals from "./pages/Deals";
import LeadCard from "./pages/LeadCard";
import DealCard from "./pages/DealCard";
import Roles from "./pages/Roles";
import Inbox from "./pages/Inbox";
import Warehouse from "./pages/Warehouse";
import Finance from "./pages/Finance";
import Clients from "./pages/Clients";
import ClientCard from "./pages/ClientCard";
import Settings from "./pages/Settings";
import Analytics from "./pages/Analytics";
import Phone from "./pages/Phone";

function Shell() {
  const { me, loading } = useAuth();
  if (loading) return <div className="spin">Загрузка…</div>;
  if (!me) return <Login />;

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/leads" replace />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadCard />} />
          <Route path="/deals" element={<Deals />} />
          <Route path="/deals/:id" element={<DealCard />} />
          <Route path="/roles" element={<Roles />} />
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/phone" element={<Phone />} />
          <Route path="/warehouse" element={<Warehouse />} />
          <Route path="/clients" element={<Clients />} />
          <Route path="/clients/:id" element={<ClientCard />} />
          <Route path="/finance" element={<Finance />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="*" element={<Navigate to="/leads" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
