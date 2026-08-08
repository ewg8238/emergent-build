import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { HardHat, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password });
      setDone(true);
      toast.success("Password updated");
      setTimeout(() => navigate("/login"), 1800);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-md fade-up">
        <Link to="/" className="flex items-center gap-2 mb-8"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></Link>
        {!token ? (
          <div data-testid="reset-invalid">
            <h1 className="font-head text-3xl mb-2">Invalid reset link</h1>
            <p className="text-neutral-600">Please use the link from your reset email, or <Link to="/forgot-password" className="underline">request a new one</Link>.</p>
          </div>
        ) : done ? (
          <div data-testid="reset-done">
            <CheckCircle2 className="w-12 h-12 mb-4 text-[var(--valid)]" />
            <h1 className="font-head text-3xl mb-2">Password updated</h1>
            <p className="text-neutral-600">Redirecting you to login…</p>
          </div>
        ) : (
          <>
            <h1 className="font-head text-3xl mb-2">Set a new password</h1>
            <p className="text-neutral-600 mb-6 text-sm">Choose a new password for your account.</p>
            <form onSubmit={submit} className="space-y-4">
              <input className="w-full border border-neutral-300 px-4 py-3 rounded-sm focus:ring-2 focus:ring-black outline-none"
                type="password" placeholder="New password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="reset-password" />
              <input className="w-full border border-neutral-300 px-4 py-3 rounded-sm focus:ring-2 focus:ring-black outline-none"
                type="password" placeholder="Confirm new password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required data-testid="reset-confirm" />
              {error && <p className="text-sm text-[var(--expired)]" data-testid="reset-error">{error}</p>}
              <button className="btn-primary w-full" disabled={loading} data-testid="reset-submit">{loading ? "Updating…" : "Update password"}</button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
