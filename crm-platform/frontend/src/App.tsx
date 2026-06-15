import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Leads from "./pages/Leads";
import Deals from "./pages/Deals";
import DealCard from "./pages/DealCard";
import Roles from "./pages/Roles";
import Placeholder from "./pages/Placeholder";

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
          <Route path="/deals" element={<Deals />} />
          <Route path="/deals/:id" element={<DealCard />} />
          <Route path="/roles" element={<Roles />} />
          <Route path="/inbox" element={<Placeholder title="Чаты · Открытые линии" note="Единый inbox мессенджеров (Telegram, Instagram, Facebook, WhatsApp, Viber, Google Business)." />} />
          <Route path="/phone" element={<Placeholder title="Телефония" note="Связка с SIP-шлюзом на Hetzner: журнал звонков, запись, click-to-call из карточки." />} />
          <Route path="/warehouse" element={<Placeholder title="Товары · Склад" note="Партионный учёт (FIFO), приходные/расходные накладные, инвентаризация." />} />
          <Route path="/clients" element={<Placeholder title="Клиенты" note="Контакты и компании с историей сделок и каналами связи." />} />
          <Route path="/finance" element={<Placeholder title="Финансы" note="Замена Finmap: cashflow, кассы, P&L. Виден только по праву finance.view." />} />
          <Route path="/analytics" element={<Placeholder title="Аналитика" note="Конверсия по воронкам, средний чек, отчёты по менеджерам." />} />
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
