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
import Tasks from "./pages/Tasks";
import Duplicates from "./pages/Duplicates";
import Razvitok from "./pages/Razvitok";
import ContactCenter from "./pages/ContactCenter";
import Warehouse from "./pages/Warehouse";
import WarehouseWork from "./pages/WarehouseWork";
import Finance from "./pages/Finance";
import Clients from "./pages/Clients";
import ClientCard from "./pages/ClientCard";
import Settings from "./pages/Settings";
import Analytics from "./pages/Analytics";
import MetaMarketing from "./pages/MetaMarketing";
import AiCosts from "./pages/AiCosts";
import AiCenter from "./pages/AiCenter";
import WhatsNew from "./pages/WhatsNew";
import Phone from "./pages/Phone";
import Employees from "./pages/Employees";
import InviteAccept from "./InviteAccept";

function Shell() {
  const { me, loading } = useAuth();
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/invite/")) {
    return (<BrowserRouter><Routes><Route path="/invite/:token" element={<InviteAccept />} /><Route path="*" element={<InviteAccept />} /></Routes></BrowserRouter>);
  }
  if (loading) return <div className="spin">Загрузка…</div>;
  if (!me) return <Login />;

  // Доступ до розділу: немає права — сторінка не відкривається навіть за прямим лінком
  const Guard = ({ perm, children }: { perm: string; children: any }) => {
    const { can } = useAuth();
    if (!can(perm)) return <div className="muted" style={{ padding: 40, fontSize: 15 }}>Немає доступу до цього розділу</div>;
    return children;
  };
  const homePath = me?.is_superuser ? "/leads"
    : (me?.permissions || []).includes("lead.view") ? "/leads"
    : (me?.permissions || []).includes("deal.view") ? "/deals"
    : (me?.permissions || []).includes("inbox.view") ? "/inbox"
    : (me?.permissions || []).includes("task.view") ? "/tasks"
    : (me?.permissions || []).includes("analytics.view") ? "/analytics"
    : (me?.permissions || []).includes("marketing.view") ? "/analytics"
    : (me?.permissions || []).includes("contact.view") ? "/clients"
    : "/profile";

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to={homePath} replace />} />
          <Route path="/leads" element={<Guard perm="lead.view"><Leads /></Guard>} />
          <Route path="/leads/:id" element={<Guard perm="lead.view"><LeadCard /></Guard>} />
          <Route path="/deals" element={<Guard perm="deal.view"><Deals /></Guard>} />
          <Route path="/deals/:id" element={<Guard perm="deal.view"><DealCard /></Guard>} />
          <Route path="/roles" element={<Roles />} />
          <Route path="/employees" element={<Employees />} />
          <Route path="/inbox" element={<Guard perm="inbox.view"><Inbox /></Guard>} />
          <Route path="/tasks" element={<Guard perm="task.view"><Tasks /></Guard>} />
          <Route path="/contact-center" element={<ContactCenter />} />
          <Route path="/phone" element={<Phone />} />
          <Route path="/warehouse" element={<Warehouse />} />
          <Route path="/wh" element={<WarehouseWork />} />
          <Route path="/clients" element={<Guard perm="contact.view"><Clients /></Guard>} />
          <Route path="/clients/:id" element={<ClientCard />} />
          <Route path="/duplicates" element={<Duplicates />} />
          <Route path="/development" element={<Razvitok />} />
          <Route path="/finance" element={<Finance />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/marketing/meta" element={<MetaMarketing />} />
          <Route path="/ai-costs" element={<AiCenter />} />
          <Route path="/whats-new" element={<WhatsNew />} />
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
