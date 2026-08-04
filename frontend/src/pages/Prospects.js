import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import api from "@/lib/api";
import { toast } from "sonner";
import { Play, Mail, Clock } from "lucide-react";

const COLS = [
  { key: "NEW", label: "New" },
  { key: "EMAILED", label: "Emailed" },
  { key: "RESPONDED", label: "Responded" },
  { key: "CONVERTED", label: "Converted" },
];
const NEXT = { NEW: "EMAILED", EMAILED: "RESPONDED", RESPONDED: "CONVERTED", CONVERTED: "CONVERTED" };

export default function Prospects() {
  const [prospects, setProspects] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get("/prospects"); setProspects(data); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const runPipeline = async () => {
    const t = toast.loading("Running Apollo prospecting pipeline…");
    try {
      const { data } = await api.post("/cron/prospecting");
      toast.success(`${data.added} new leads added to a ${data.sequence_steps}-step sequence`, { id: t });
      load();
    } catch { toast.error("Pipeline failed", { id: t }); }
  };

  const advance = async (p) => {
    const next = NEXT[p.outreach_status];
    await api.patch(`/prospects/${p.id}`, { outreach_status: next });
    load();
  };

  return (
    <div>
      <Nav />
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-2">
          <div>
            <p className="mono text-sm text-neutral-500">Outbound Engine</p>
            <h1 className="font-head text-4xl">GC Prospecting Pipeline</h1>
          </div>
          <button className="btn-primary !py-2.5 !px-4 flex items-center gap-2 text-sm" onClick={runPipeline} data-testid="run-pipeline-btn">
            <Play className="w-4 h-4" /> Run Prospecting Pipeline
          </button>
        </div>
        <p className="text-neutral-600 mb-8 text-sm max-w-2xl">Mocked Apollo.io lead sourcing → dedupe against contractors & prospects → 3-step Instantly.ai email sequence. <span className="mono">(SIMULATED for demo)</span></p>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {COLS.map((col) => {
            const items = prospects.filter((p) => p.outreach_status === col.key);
            return (
              <div key={col.key} className="border border-neutral-200 bg-white" data-testid={`col-${col.key}`}>
                <div className="px-4 py-3 border-b border-neutral-200 flex items-center justify-between">
                  <span className="font-head text-lg">{col.label}</span>
                  <span className="mono text-sm text-neutral-400">{items.length}</span>
                </div>
                <div className="p-3 space-y-3 min-h-[120px]">
                  {loading ? <p className="text-neutral-400 text-sm p-2 mono">Loading…</p> :
                    items.map((p) => (
                      <div key={p.id} className="border border-neutral-200 p-3 card-hover" data-testid={`prospect-${p.id}`}>
                        <div className="font-medium text-sm">{p.company_name}</div>
                        <div className="text-xs text-neutral-500">{p.contact_name} • {p.title}</div>
                        <div className="text-xs text-neutral-400 mono mt-1 flex items-center gap-1"><Mail className="w-3 h-3" />{p.email}</div>
                        {p.outreach_status !== "CONVERTED" && (
                          <button className="btn-outline !py-1 !px-3 !text-xs mt-3 flex items-center gap-1" onClick={() => advance(p)} data-testid={`advance-${p.id}`}>
                            <Clock className="w-3 h-3" /> Advance → {NEXT[p.outreach_status]}
                          </button>
                        )}
                      </div>
                    ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
