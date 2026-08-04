import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import api from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Palette, Upload, Users, ShieldAlert, Save, CalendarClock, Link as LinkIcon } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TIMEZONES = ["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix", "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Mexico_City", "America/Sao_Paulo", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney"];

export default function Settings() {
  const { refresh } = useAuth();
  const [settings, setSettings] = useState(null);
  const [recipients, setRecipients] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    const { data } = await api.get("/settings");
    setSettings(data);
    setRecipients((data.report_recipients || []).join(", "));
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const list = recipients.split(",").map((s) => s.trim()).filter(Boolean);
      await api.put("/settings", {
        brand_color: settings.brand_color,
        escalation_threshold: settings.escalation_threshold,
        report_recipients: list,
        report_day: settings.report_day,
        report_hour: settings.report_hour,
        timezone: settings.timezone,
        slug: settings.slug,
      });
      toast.success("Settings saved");
      load();
    } catch { toast.error("Failed to save settings"); }
    finally { setSaving(false); }
  };

  const uploadLogo = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/settings/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setSettings((s) => ({ ...s, logo_url: data.logo_url }));
      toast.success("Logo uploaded");
      refresh();
    } catch { toast.error("Logo upload failed"); }
    finally { setUploading(false); }
  };

  if (!settings) return <div><Nav /><div className="p-24 text-center mono">Loading…</div></div>;

  return (
    <div>
      <Nav />
      <div className="max-w-3xl mx-auto px-6 py-10 fade-up">
        <p className="mono text-sm text-neutral-500">Company Settings</p>
        <h1 className="font-head text-4xl mb-8">Branding & Reports</h1>

        <div className="space-y-6">
          {/* Branding */}
          <div className="border border-neutral-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-4"><Palette className="w-5 h-5" /><h2 className="font-head text-xl">Report Branding</h2></div>
            <div className="grid sm:grid-cols-2 gap-6">
              <div>
                <label className="text-sm font-medium">Company logo</label>
                <div className="mt-2 flex items-center gap-4">
                  <div className="w-24 h-16 border border-neutral-200 flex items-center justify-center overflow-hidden bg-neutral-50">
                    {settings.logo_url
                      ? <img src={`${BACKEND_URL}${settings.logo_url}`} alt="logo" className="max-h-full max-w-full object-contain" data-testid="logo-preview" />
                      : <span className="text-xs text-neutral-400">No logo</span>}
                  </div>
                  <label className="btn-outline !py-2 !px-3 text-sm flex items-center gap-2 cursor-pointer" data-testid="logo-upload-label">
                    <Upload className="w-4 h-4" /> {uploading ? "Uploading…" : "Upload"}
                    <input type="file" accept="image/*" className="hidden" onChange={uploadLogo} data-testid="logo-input" />
                  </label>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Brand color</label>
                <div className="mt-2 flex items-center gap-3">
                  <input type="color" value={settings.brand_color} onChange={(e) => setSettings({ ...settings, brand_color: e.target.value })}
                    className="w-12 h-10 border border-neutral-200 cursor-pointer" data-testid="brand-color-input" />
                  <span className="mono text-sm">{settings.brand_color}</span>
                </div>
                <p className="text-xs text-neutral-400 mt-2">Used on PDF headers and report emails.</p>
              </div>
            </div>
          </div>

          {/* Escalation */}
          <div className="border border-neutral-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-4"><ShieldAlert className="w-5 h-5" /><h2 className="font-head text-xl">Escalation Threshold</h2></div>
            <p className="text-sm text-neutral-600 mb-3">Alert me directly after a subcontractor ignores this many reminders.</p>
            <Select value={String(settings.escalation_threshold)} onValueChange={(v) => setSettings({ ...settings, escalation_threshold: Number(v) })}>
              <SelectTrigger className="w-[220px] rounded-sm" data-testid="threshold-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[2, 3, 5].map((n) => <SelectItem key={n} value={String(n)} data-testid={`threshold-${n}`}>{n} ignored reminders</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {/* Recipients */}
          <div className="border border-neutral-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-4"><Users className="w-5 h-5" /><h2 className="font-head text-xl">Weekly Report Recipients</h2></div>
            <p className="text-sm text-neutral-600 mb-3">Extra teammates who also get the Monday compliance email (comma-separated). You always receive it.</p>
            <input value={recipients} onChange={(e) => setRecipients(e.target.value)} placeholder="ops@yourco.com, pm@yourco.com"
              className="w-full border border-neutral-300 px-4 py-3 rounded-sm focus:ring-2 focus:ring-black outline-none" data-testid="recipients-input" />
          </div>

          {/* Schedule */}
          <div className="border border-neutral-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-4"><CalendarClock className="w-5 h-5" /><h2 className="font-head text-xl">Report Schedule</h2></div>
            <p className="text-sm text-neutral-600 mb-3">Pick the day and time (UTC) your weekly compliance email is sent.</p>
            <div className="flex flex-wrap gap-3">
              <Select value={String(settings.report_day)} onValueChange={(v) => setSettings({ ...settings, report_day: Number(v) })}>
                <SelectTrigger className="w-[180px] rounded-sm" data-testid="report-day-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DAYS.map((d, i) => <SelectItem key={d} value={String(i)} data-testid={`day-${i}`}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={String(settings.report_hour)} onValueChange={(v) => setSettings({ ...settings, report_hour: Number(v) })}>
                <SelectTrigger className="w-[160px] rounded-sm" data-testid="report-hour-select"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-64">
                  {Array.from({ length: 24 }).map((_, h) => <SelectItem key={h} value={String(h)} data-testid={`hour-${h}`}>{String(h).padStart(2, "0")}:00</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={settings.timezone} onValueChange={(v) => setSettings({ ...settings, timezone: v })}>
                <SelectTrigger className="w-[220px] rounded-sm" data-testid="timezone-select"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-64">
                  {TIMEZONES.map((tz) => <SelectItem key={tz} value={tz} data-testid={`tz-${tz}`}>{tz.replace("_", " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Portal link */}
          <div className="border border-neutral-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-4"><LinkIcon className="w-5 h-5" /><h2 className="font-head text-xl">Branded Upload Portal</h2></div>
            <p className="text-sm text-neutral-600 mb-3">Your subcontractor upload links carry your company name. Customize the slug below.</p>
            <div className="flex items-center border border-neutral-300 rounded-sm overflow-hidden">
              <span className="px-3 py-3 bg-neutral-100 text-sm text-neutral-500 mono whitespace-nowrap">{BACKEND_URL}/u/</span>
              <input value={settings.slug || ""} onChange={(e) => setSettings({ ...settings, slug: e.target.value })}
                className="flex-1 px-3 py-3 outline-none mono text-sm" data-testid="slug-input" />
            </div>
            <p className="text-xs text-neutral-400 mt-2">Note: a full custom subdomain (e.g. skyline.coiautopilot.com) requires DNS setup at deploy time; this branded path works today.</p>
          </div>

          <button className="btn-primary flex items-center gap-2" onClick={save} disabled={saving} data-testid="save-settings-btn">
            <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
