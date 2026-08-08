import { useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { HardHat, MailCheck } from "lucide-react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-md fade-up">
        <Link to="/" className="flex items-center gap-2 mb-8"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></Link>
        {sent ? (
          <div data-testid="forgot-sent">
            <MailCheck className="w-12 h-12 mb-4 text-[var(--valid)]" />
            <h1 className="font-head text-3xl mb-2">Check your email</h1>
            <p className="text-neutral-600">If an account exists for <b>{email}</b>, we've sent a reset link. It expires in 1 hour.</p>
            <Link to="/login" className="underline text-sm mt-6 inline-block">Back to login</Link>
          </div>
        ) : (
          <>
            <h1 className="font-head text-3xl mb-2">Forgot password</h1>
            <p className="text-neutral-600 mb-6 text-sm">Enter your email and we'll send you a secure reset link.</p>
            <form onSubmit={submit} className="space-y-4">
              <input className="w-full border border-neutral-300 px-4 py-3 rounded-sm focus:ring-2 focus:ring-black outline-none"
                type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="forgot-email" />
              {error && <p className="text-sm text-[var(--expired)]" data-testid="forgot-error">{error}</p>}
              <button className="btn-primary w-full" disabled={loading} data-testid="forgot-submit">{loading ? "Sending…" : "Send reset link"}</button>
            </form>
            <p className="text-sm text-neutral-600 mt-6"><Link to="/login" className="underline">Back to login</Link></p>
          </>
        )}
      </div>
    </div>
  );
}
