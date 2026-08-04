import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { HardHat } from "lucide-react";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ company_name: "", email: "", phone: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await register(form);
      navigate("/onboarding");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-md fade-up">
        <Link to="/" className="flex items-center gap-2 mb-8"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></Link>
        <h1 className="font-head text-3xl mb-2">Start your free trial</h1>
        <p className="text-neutral-600 mb-6 text-sm">14 days free. No card required to create your account.</p>
        <form onSubmit={submit} className="space-y-4">
          {[["Company name", "company_name", "text"], ["Work email", "email", "email"], ["Phone", "phone", "tel"], ["Password", "password", "password"]].map(([label, key, type]) => (
            <div key={key}>
              <label className="text-sm font-medium">{label}</label>
              <input className="w-full border border-neutral-300 px-4 py-3 mt-1 rounded-sm focus:ring-2 focus:ring-black outline-none"
                type={type} value={form[key]} onChange={set(key)} required={key !== "phone"} data-testid={`register-${key}`} />
            </div>
          ))}
          {error && <p className="text-sm text-[var(--expired)]" data-testid="register-error">{error}</p>}
          <button className="btn-primary w-full" disabled={loading} data-testid="register-submit">{loading ? "Creating…" : "Create Account"}</button>
        </form>
        <p className="text-sm text-neutral-600 mt-6">Already have an account? <Link to="/login" className="underline">Log in</Link></p>
      </div>
    </div>
  );
}
