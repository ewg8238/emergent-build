import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Nav from "@/components/Nav";
import api from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";
import { ArrowLeft } from "lucide-react";

export default function InviteSubcontractor() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ company_name: "", contact_name: "", email: "", phone: "" });
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/subcontractors/invite", form);
      toast.success("Invite sent — upload link delivered via email & SMS");
      console.log("Upload link:", data.upload_link);
      navigate("/dashboard");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div>
      <Nav />
      <div className="max-w-xl mx-auto px-6 py-12 fade-up">
        <button className="flex items-center gap-2 text-sm text-neutral-500 mb-6 hover:text-black" onClick={() => navigate("/dashboard")} data-testid="back-btn">
          <ArrowLeft className="w-4 h-4" /> Back to dashboard
        </button>
        <h1 className="font-head text-4xl mb-2">Invite a Subcontractor</h1>
        <p className="text-neutral-600 mb-8">We'll email and text them a secure link to upload their Certificate of Insurance.</p>
        <form onSubmit={submit} className="space-y-4">
          {[["Company Name", "company_name", "text", true], ["Contact Name", "contact_name", "text", true], ["Email", "email", "email", true], ["Phone", "phone", "tel", false]].map(([label, key, type, req]) => (
            <div key={key}>
              <label className="text-sm font-medium">{label}</label>
              <input className="w-full border border-neutral-300 px-4 py-3 mt-1 rounded-sm focus:ring-2 focus:ring-black outline-none"
                type={type} value={form[key]} onChange={set(key)} required={req} data-testid={`invite-${key}`} />
            </div>
          ))}
          <button className="btn-primary w-full" disabled={loading} data-testid="invite-submit">{loading ? "Sending…" : "Send Upload Invite"}</button>
        </form>
      </div>
    </div>
  );
}
