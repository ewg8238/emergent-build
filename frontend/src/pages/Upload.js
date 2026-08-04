import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { UploadCloud, CheckCircle2, HardHat, FileText } from "lucide-react";

const BG = "https://images.unsplash.com/photo-1503387762-592deb58ef4e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";

export default function Upload() {
  const [params] = useSearchParams();
  const sub_id = params.get("sub_id") || "";
  const gc_id = params.get("gc_id") || "";
    const token = params.get("token") || "";
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true); setError("");
    const fd = new FormData();
    fd.append("sub_id", sub_id);
    fd.append("gc_id", gc_id);
    fd.append("token", token);
    fd.append("file", file);
    try {
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed. Please try again with a clear photo or PDF of your COI.");
    } finally { setLoading(false); }
  };

  const invalidLink = !sub_id || !gc_id || !token;

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:block relative">
        <img src={BG} alt="blueprint" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-black/50" />
        <div className="relative p-12 text-white h-full flex flex-col justify-between">
          <div className="flex items-center gap-2"><HardHat className="w-6 h-6" /><span className="font-head text-xl">COI Autopilot</span></div>
          <div>
            <h2 className="font-head text-4xl leading-tight">Upload your Certificate of Insurance</h2>
            <p className="text-white/70 mt-3">Our AI reads it instantly — no forms to fill out.</p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md fade-up">
          {invalidLink ? (
            <div className="text-center">
              <FileText className="w-10 h-10 mx-auto mb-4 text-neutral-400" />
              <h1 className="font-head text-2xl">Invalid upload link</h1>
              <p className="text-neutral-600 mt-2">Please use the link sent to you by your general contractor.</p>
            </div>
          ) : result ? (
            <div className="text-center" data-testid="upload-confirmation">
              <CheckCircle2 className="w-14 h-14 mx-auto mb-4 text-[var(--valid)]" />
              <h1 className="font-head text-3xl mb-2">Thank you!</h1>
              <p className="text-neutral-600">Your COI was received and processed automatically.</p>
              <div className="mt-6 border border-neutral-200 p-5 text-left text-sm space-y-1">
                <div className="flex justify-between"><span className="text-neutral-500">Status</span><span className={`status-pill status-${result.status}`}>{result.status}</span></div>
                {result.parsed?.gl_policy_number && <div className="flex justify-between"><span className="text-neutral-500">Policy #</span><span className="mono">{result.parsed.gl_policy_number}</span></div>}
                {result.parsed?.gl_expiration_date && <div className="flex justify-between"><span className="text-neutral-500">Expires</span><span className="mono">{result.parsed.gl_expiration_date}</span></div>}
                {result.review_reason && <p className="text-neutral-500 pt-2">{result.review_reason}</p>}
              </div>
            </div>
          ) : (
            <form onSubmit={submit}>
              <h1 className="font-head text-3xl mb-2">Upload your COI</h1>
              <p className="text-neutral-600 mb-6 text-sm">Accepted: PDF, JPG or PNG. A clear photo of your ACORD certificate works great.</p>
              <label className="border-2 border-dashed border-neutral-300 rounded-sm p-10 flex flex-col items-center justify-center cursor-pointer hover:border-black transition-colors" data-testid="upload-dropzone">
                <UploadCloud className="w-10 h-10 text-neutral-400 mb-3" />
                <span className="text-sm text-neutral-600">{file ? file.name : "Tap to choose a file"}</span>
                <input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => setFile(e.target.files[0])} data-testid="upload-file-input" />
              </label>
              {error && <p className="text-sm text-[var(--expired)] mt-3" data-testid="upload-error">{error}</p>}
              <button className="btn-primary w-full mt-6" disabled={!file || loading} data-testid="upload-submit">
                {loading ? "Analyzing with AI…" : "Submit COI"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
