import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import InviteSubcontractor from "@/pages/InviteSubcontractor";
import Upload from "@/pages/Upload";
import Prospects from "@/pages/Prospects";
import Settings from "@/pages/Settings";
import PaymentResult from "@/pages/PaymentResult";
import "@/App.css";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="p-24 text-center mono">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/payment/success" element={<PaymentResult />} />
            <Route path="/payment/cancel" element={<PaymentResult />} />
            <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
            <Route path="/invite-subcontractor" element={<Protected><InviteSubcontractor /></Protected>} />
            <Route path="/prospects" element={<Protected><Prospects /></Protected>} />
            <Route path="/settings" element={<Protected><Settings /></Protected>} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" />
      </AuthProvider>
    </div>
  );
}

export default App;
