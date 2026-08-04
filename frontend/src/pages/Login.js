import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { HardHat } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-md fade-up">
        <Link to="/" className="flex items-center gap-2 mb-8"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></Link>
        <h1 className="font-head text-3xl mb-6">Client Login</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-sm font-medium">Email</label>
            <input className="w-full border border-neutral-300 px-4 py-3 mt-1 rounded-sm focus:ring-2 focus:ring-black outline-none"
              type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email" />
          </div>
          <div>
            <label className="text-sm font-medium">Password</label>
            <input className="w-full border border-neutral-300 px-4 py-3 mt-1 rounded-sm focus:ring-2 focus:ring-black outline-none"
              type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password" />
          </div>
          {error && <p className="text-sm text-[var(--expired)]" data-testid="login-error">{error}</p>}
          <button className="btn-primary w-full" disabled={loading} data-testid="login-submit">{loading ? "Signing in…" : "Sign In"}</button>
        </form>
        <p className="text-sm text-neutral-600 mt-6">No account? <Link to="/register" className="underline">Start a free trial</Link></p>
      </div>
    </div>
  );
}
