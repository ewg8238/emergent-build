import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Nav from "@/components/Nav";
import { toast } from "sonner";
import api from "@/lib/api";
import { ScanText, MessageSquareWarning, LayoutDashboard, Check, ArrowRight, Building2 } from "lucide-react";

const HERO = "https://images.pexels.com/photos/31197870/pexels-photo-31197870.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";

export default function Landing() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const scrollToPricing = () => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" });

  const startCheckout = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/payments/checkout", {
        lookup_key: "pro_monthly",
        origin_url: window.location.origin,
      });
      window.location.href = data.checkout_url;
    } catch {
      toast.error("Could not start checkout. Create an account first, then subscribe.");
      navigate("/register");
    } finally {
      setLoading(false);
    }
  };

  const features = [
    { icon: ScanText, title: "AI COI Extraction", desc: "Upload any Certificate of Insurance — our vision AI reads the policy number, expiration and liability limits. Zero manual entry.", span: "md:col-span-8" },
    { icon: MessageSquareWarning, title: "Background SMS + Email Drips", desc: "Automatic 30-day pre-expiration outreach nudges subs to renew before coverage lapses.", span: "md:col-span-4" },
    { icon: LayoutDashboard, title: "Live Trade Dashboard", desc: "Color-coded green / red / orange status tags across every subcontractor, filterable in real time.", span: "md:col-span-12" },
  ];

  return (
    <div>
      <Nav />
      {/* HERO */}
      <section className="relative">
        <div className="absolute inset-0">
          <img src={HERO} alt="steel framework" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-black/60" />
        </div>
        <div className="relative max-w-7xl mx-auto px-6 py-28 md:py-40 text-white fade-up">
          <p className="mono text-sm uppercase tracking-widest text-white/70 mb-4">COI Compliance Autopilot</p>
          <h1 className="font-head text-4xl sm:text-5xl lg:text-7xl max-w-4xl leading-[1.02]">
            Stop Chasing Subcontractors. Automate Your COI Compliance.
          </h1>
          <p className="text-lg text-white/80 mt-6 max-w-2xl">
            Track, parse and enforce subcontractor insurance compliance automatically — powered by AI parsing and background reminder drips.
          </p>
          <div className="flex flex-wrap gap-4 mt-10">
            <button className="btn-primary !bg-white !text-black !border-white flex items-center gap-2" onClick={scrollToPricing} data-testid="hero-trial-btn">
              Start 14-Day Free Trial <ArrowRight className="w-4 h-4" />
            </button>
            <Link to="/login" className="btn-outline !text-white !border-white" data-testid="hero-login-btn">Client Login</Link>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="max-w-7xl mx-auto px-6 py-24">
        <h2 className="font-head text-3xl md:text-4xl mb-3">Everything a GC needs to stay compliant</h2>
        <p className="text-neutral-600 mb-12 max-w-xl">Built for general contractors managing dozens of trades across active job sites.</p>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          {features.map((f) => (
            <div key={f.title} className={`card-hover border border-neutral-200 bg-white p-8 ${f.span}`} data-testid={`feature-${f.title.replace(/\s+/g, "-").toLowerCase()}`}>
              <f.icon className="w-8 h-8 mb-6" strokeWidth={1.5} />
              <h3 className="font-head text-2xl mb-2">{f.title}</h3>
              <p className="text-neutral-600 text-base">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="max-w-7xl mx-auto px-6 py-24">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <h2 className="font-head text-4xl md:text-5xl mb-4">One plan. Everything included.</h2>
            <p className="text-neutral-600 text-lg">Unlimited subcontractors, AI parsing, automated drips and the live compliance dashboard.</p>
          </div>
          <div className="border-2 border-black bg-white p-10" data-testid="pricing-card">
            <div className="flex items-center gap-2 mb-2"><Building2 className="w-5 h-5" /><span className="mono uppercase text-sm tracking-widest">Pro Plan</span></div>
            <div className="flex items-end gap-2 mb-6">
              <span className="font-head text-6xl">$149</span><span className="text-neutral-500 mb-2">/ month</span>
            </div>
            <ul className="space-y-3 mb-8">
              {["Unlimited subcontractors", "AI COI extraction", "Automated SMS + email drips", "Live compliance dashboard", "14-day free trial"].map((t) => (
                <li key={t} className="flex items-center gap-3 text-sm"><Check className="w-4 h-4 text-[var(--valid)]" /> {t}</li>
              ))}
            </ul>
            <button className="btn-primary w-full" onClick={startCheckout} disabled={loading} data-testid="subscribe-btn">
              {loading ? "Redirecting…" : "Start 14-Day Free Trial"}
            </button>
          </div>
        </div>
      </section>

      <footer className="border-t border-neutral-200 py-10 text-center text-sm text-neutral-500">
        COI Autopilot — Automated Subcontractor Insurance Compliance
      </footer>
    </div>
  );
}
