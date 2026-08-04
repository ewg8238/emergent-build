import { useEffect, useState } from "react";
import { useSearchParams, useLocation, Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CheckCircle2, XCircle, HardHat } from "lucide-react";

export default function PaymentResult() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const cancelled = location.pathname.includes("cancel");
  const sessionId = params.get("session_id");
  const [state, setState] = useState(cancelled ? "cancelled" : "checking");

  useEffect(() => {
    if (cancelled || !sessionId) return;
    let tries = 0;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") { setState("paid"); refresh(); return; }
        if (["expired", "failed"].includes(data.payment_status)) { setState("failed"); return; }
      } catch {}
      if (tries++ < 8) setTimeout(poll, 2000); else setState("timeout");
    };
    poll();
  }, [sessionId, cancelled]);

  const configs = {
    checking: { icon: HardHat, color: "#111", title: "Confirming your payment…", desc: "Hang tight, this only takes a moment." },
    paid: { icon: CheckCircle2, color: "var(--valid)", title: "You're all set!", desc: "Your Pro subscription is active." },
    cancelled: { icon: XCircle, color: "var(--review)", title: "Checkout cancelled", desc: "No charge was made." },
    failed: { icon: XCircle, color: "var(--expired)", title: "Payment failed", desc: "Please try again." },
    timeout: { icon: HardHat, color: "#111", title: "Still processing", desc: "Check your dashboard shortly." },
  };
  const c = configs[state];

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="text-center max-w-md fade-up" data-testid="payment-result">
        <c.icon className="w-16 h-16 mx-auto mb-5" style={{ color: c.color }} />
        <h1 className="font-head text-4xl mb-2">{c.title}</h1>
        <p className="text-neutral-600 mb-8">{c.desc}</p>
        <button className="btn-primary" onClick={() => navigate("/dashboard")} data-testid="goto-dashboard-btn">Go to Dashboard</button>
      </div>
    </div>
  );
}
