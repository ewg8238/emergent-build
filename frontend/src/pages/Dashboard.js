import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Nav from "@/components/Nav";
import { StatusPill } from "@/components/StatusPill";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { Plus, Search, RefreshCw, Bell, CheckCircle2, AlertTriangle, XCircle, FileWarning } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const money = (n) => (n == null ? "—" : `$${Number(n).toLocaleString()}`);

export default function Dashboard() {
  const { user } = useAuth();
  const [docs, setDocs] = useState([]);
  const [stats, setStats] = useState({ total: 0, VALID: 0, EXPIRED: 0, NEEDS_REVIEW: 0, INSUFFICIENT: 0 });
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("ALL");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [d, s] = await Promise.all([api.get("/compliance-documents"), api.get("/dashboard/stats")]);
      setDocs(d.data); setStats(s.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const runReminders = async () => {
    const t = toast.loading("Scanning for expiring COIs…");
    try {
      const { data } = await api.post("/cron/check-expirations");
      toast.success(`Scanned ${data.scanned} docs • ${data.nudged} reminders sent`, { id: t });
      load();
    } catch { toast.error("Failed to run reminders", { id: t }); }
  };

  const filtered = docs.filter((d) => {
    const matchQ = !q || d.subcontractor_name?.toLowerCase().includes(q.toLowerCase()) || (d.gl_policy_number || "").toLowerCase().includes(q.toLowerCase());
    const matchS = status === "ALL" || d.status === status;
    return matchQ && matchS;
  });

  const cards = [
    { label: "Total", value: stats.total, icon: FileWarning, color: "#111" },
    { label: "Valid", value: stats.VALID, icon: CheckCircle2, color: "var(--valid)" },
    { label: "Expired", value: stats.EXPIRED, icon: XCircle, color: "var(--expired)" },
    { label: "Review / Insufficient", value: (stats.NEEDS_REVIEW || 0) + (stats.INSUFFICIENT || 0), icon: AlertTriangle, color: "var(--review)" },
  ];

  return (
    <div>
      <Nav />
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <p className="mono text-sm text-neutral-500">{user?.company_name}</p>
            <h1 className="font-head text-4xl">Compliance Dashboard</h1>
          </div>
          <div className="flex gap-3">
            <button className="btn-outline !py-2.5 !px-4 flex items-center gap-2 text-sm" onClick={runReminders} data-testid="run-reminders-btn">
              <Bell className="w-4 h-4" /> Run Reminder Drip
            </button>
            <Link to="/invite-subcontractor" className="btn-primary !py-2.5 !px-4 flex items-center gap-2 text-sm" data-testid="invite-sub-btn">
              <Plus className="w-4 h-4" /> Invite Subcontractor
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {cards.map((c) => (
            <div key={c.label} className="border border-neutral-200 bg-white p-6" data-testid={`stat-${c.label}`}>
              <c.icon className="w-5 h-5 mb-3" style={{ color: c.color }} />
              <div className="font-head text-4xl" style={{ color: c.color }}>{c.value}</div>
              <div className="text-sm text-neutral-500 mt-1">{c.label}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 mb-4">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
            <input className="w-full border border-neutral-300 pl-10 pr-4 py-2.5 rounded-sm focus:ring-2 focus:ring-black outline-none"
              placeholder="Search subcontractor or policy #" value={q} onChange={(e) => setQ(e.target.value)} data-testid="search-input" />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[200px] rounded-sm" data-testid="status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["ALL", "VALID", "EXPIRED", "NEEDS_REVIEW", "INSUFFICIENT"].map((s) => (
                <SelectItem key={s} value={s} data-testid={`filter-${s}`}>{s === "ALL" ? "All statuses" : s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <button className="btn-outline !py-2.5 !px-4" onClick={load} data-testid="refresh-btn"><RefreshCw className="w-4 h-4" /></button>
        </div>

        <div className="border border-neutral-200 bg-white overflow-x-auto">
          <table className="w-full text-sm" data-testid="compliance-table">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-neutral-500">
                {["Subcontractor", "Policy #", "GL Limit", "Expiration", "Status", "Notes"].map((h) => (
                  <th key={h} className="px-4 py-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-neutral-400 mono">Loading…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-neutral-400">No documents. Invite a subcontractor to begin.</td></tr>
              ) : filtered.map((d) => (
                <tr key={d.id} className="border-b border-neutral-100 hover:bg-neutral-50 transition-colors" data-testid={`doc-row-${d.id}`}>
                  <td className="px-4 py-3">
                    <div className="font-medium">{d.subcontractor_name}</div>
                    <div className="text-xs text-neutral-400">{d.contact_email}</div>
                  </td>
                  <td className="px-4 py-3 mono">{d.gl_policy_number || "—"}</td>
                  <td className="px-4 py-3 mono">{money(d.general_liability_limit)}</td>
                  <td className="px-4 py-3 mono">{d.gl_expiration_date || "—"}</td>
                  <td className="px-4 py-3"><StatusPill status={d.status} /></td>
                  <td className="px-4 py-3 text-xs text-neutral-500 max-w-[220px]">{d.review_reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
