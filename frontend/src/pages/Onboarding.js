import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";
import { HardHat, Palette, Upload as UploadIcon, UserPlus, Check, ArrowRight } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [brand, setBrand] = useState("#111111");
  const [logoUrl, setLogoUrl] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [sub, setSub] = useState({ company_name: "", contact_name: "", email: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const setS = (k) => (e) => setSub({ ...sub, [k]: e.target.value });

  const uploadLogo = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/settings/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setLogoUrl(data.logo_url);
      toast.success("Logo uploaded");
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const saveBrandNext = async () => {
    setBusy(true);
    try {
      await api.put("/settings", { brand_color: brand });
      setStep(2);
    } catch { toast.error("Could not save branding"); }
    finally { setBusy(false); }
  };

  const inviteNext = async () => {
    if (!sub.company_name || !sub.contact_name || !sub.email) { setStep(3); return; }
    setBusy(true);
    try {
      await api.post("/subcontractors/invite", sub);
      toast.success("Invite sent");
      setStep(3);
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const finish = async () => {
    setBusy(true);
    try { await api.put("/settings", { onboarded: true }); } catch {}
    navigate("/dashboard");
  };

  const steps = [
    { n: 1, label: "Branding", icon: Palette },
    { n: 2, label: "First invite", icon: UserPlus },
    { n: 3, label: "Done", icon: Check },
  ];

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-lg fade-up">
        <div className="flex items-center gap-2 mb-8"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></div>

        <div className="flex items-center gap-3 mb-8">
          {steps.map((s) => (
            <div key={s.n} className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
                style={{ background: step >= s.n ? brand : "#eee", color: step >= s.n ? "#fff" : "#999" }} data-testid={`step-dot-${s.n}`}>
                {step > s.n ? <Check className="w-4 h-4" /> : s.n}
              </div>
              <span className={`text-sm ${step >= s.n ? "font-medium" : "text-neutral-400"}`}>{s.label}</span>
              {s.n < 3 && <div className="w-6 h-px bg-neutral-200" />}
            </div>
          ))}
        </div>

        {step === 1 && (
          <div data-testid="onboarding-step-1">
            <h1 className="font-head text-3xl mb-2">Make it yours</h1>
            <p className="text-neutral-600 mb-6 text-sm">Add your logo and brand color — they appear on reports and your subcontractor upload portal.</p>
            <div className="border border-neutral-200 p-6 space-y-5">
              <div>
                <label className="text-sm font-medium">Company logo</label>
                <div className="mt-2 flex items-center gap-4">
                  <div className="w-24 h-16 border border-neutral-200 flex items-center justify-center overflow-hidden bg-neutral-50">
                    {logoUrl ? <img src={`${BACKEND_URL}${logoUrl}`} alt="logo" className="max-h-full max-w-full object-contain" data-testid="onboarding-logo-preview" /> : <span className="text-xs text-neutral-400">No logo</span>}
                  </div>
                  <label className="btn-outline !py-2 !px-3 text-sm flex items-center gap-2 cursor-pointer" data-testid="onboarding-logo-label">
                    <UploadIcon className="w-4 h-4" /> {uploading ? "Uploading…" : "Upload"}
                    <input type="file" accept="image/*" className="hidden" onChange={uploadLogo} data-testid="onboarding-logo-input" />
                  </label>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Brand color</label>
                <div className="mt-2 flex items-center gap-3">
                  <input type="color" value={brand} onChange={(e) => setBrand(e.target.value)} className="w-12 h-10 border border-neutral-200 cursor-pointer" data-testid="onboarding-color-input" />
                  <span className="mono text-sm">{brand}</span>
                </div>
              </div>
            </div>
            <button className="btn-primary w-full mt-6 flex items-center justify-center gap-2" style={{ background: brand, borderColor: brand }} onClick={saveBrandNext} disabled={busy} data-testid="onboarding-next-1">
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {step === 2 && (
          <div data-testid="onboarding-step-2">
            <h1 className="font-head text-3xl mb-2">Invite your first subcontractor</h1>
            <p className="text-neutral-600 mb-6 text-sm">We'll text and email them a secure link to upload their COI. You can skip and do this later.</p>
            <div className="space-y-3">
              {[["Company Name", "company_name"], ["Contact Name", "contact_name"], ["Email", "email"], ["Phone", "phone"]].map(([label, key]) => (
                <div key={key}>
                  <label className="text-sm font-medium">{label}</label>
                  <input className="w-full border border-neutral-300 px-4 py-3 mt-1 rounded-sm focus:ring-2 focus:ring-black outline-none"
                    value={sub[key]} onChange={setS(key)} data-testid={`onboarding-sub-${key}`} />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-6">
              <button className="btn-outline flex-1" onClick={() => setStep(3)} data-testid="onboarding-skip">Skip for now</button>
              <button className="btn-primary flex-1" style={{ background: brand, borderColor: brand }} onClick={inviteNext} disabled={busy} data-testid="onboarding-next-2">
                {busy ? "Sending…" : "Send invite"}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="text-center" data-testid="onboarding-step-3">
            <div className="w-16 h-16 rounded-full mx-auto flex items-center justify-center mb-5" style={{ background: brand }}>
              <Check className="w-8 h-8 text-white" />
            </div>
            <h1 className="font-head text-3xl mb-2">You're all set!</h1>
            <p className="text-neutral-600 mb-8">Your compliance dashboard is ready. Upload COIs, track statuses, and let the automation chase renewals for you.</p>
            <button className="btn-primary" style={{ background: brand, borderColor: brand }} onClick={finish} disabled={busy} data-testid="onboarding-finish">Go to Dashboard</button>
          </div>
        )}
      </div>
    </div>
  );
}
