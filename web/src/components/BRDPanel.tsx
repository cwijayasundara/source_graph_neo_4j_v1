"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";

type AttemptRecord = {
  attempt: number;
  rating: "high" | "medium" | "low";
  weighted_score: number;
  feedback: Array<{
    dimension: string;
    severity: string;
    suggestion: string;
    target_section: string;
  }>;
};

type BRDSummary = {
  id: string;
  version: number;
  rating: "high" | "medium" | "low";
  weighted_score: number;
  attempts: number;
  strategy: string;
  created_at: string;
  attempt_history: AttemptRecord[];
};

type JobStatus =
  | { status: "running" }
  | { status: "error"; error: string }
  | { status: "done"; brd_id: string; rating: string; version: number };

type LatestState = BRDSummary | JobStatus | null;

const ratingClass: Record<string, string> = {
  high: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  low: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

function isJobStatus(value: LatestState): value is JobStatus {
  return !!value && typeof value === "object" && "status" in value;
}

export default function BRDPanel({ repoId }: { repoId: string }) {
  const [latest, setLatest] = useState<LatestState>(null);
  const [loading, setLoading] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);

  const fetchLatest = async () => {
    const res = await fetch(`/api/repos/${encodeURIComponent(repoId)}/brd`);
    if (res.status === 404) {
      setLatest(null);
      return;
    }
    setLatest(await res.json());
  };

  useEffect(() => {
    fetchLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  useEffect(() => {
    if (isJobStatus(latest) && latest.status === "running") {
      const t = setInterval(fetchLatest, 3000);
      return () => clearInterval(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  const onGenerate = async () => {
    setLoading(true);
    await fetch(`/api/repos/${encodeURIComponent(repoId)}/brd`, { method: "POST" });
    await fetchLatest();
    setLoading(false);
  };

  const summary = !isJobStatus(latest) ? (latest as BRDSummary | null) : null;
  const job = isJobStatus(latest) ? latest : null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Business Requirements Document
          </h2>
        </div>
        <button
          onClick={onGenerate}
          disabled={loading || (job?.status === "running")}
          className="px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {summary ? "Re-generate" : "Generate BRD"}
        </button>
      </div>

      {!latest && (
        <p className="text-sm text-zinc-500">
          No BRD yet. Click &quot;Generate BRD&quot; to create one.
        </p>
      )}

      {job?.status === "running" && (
        <p className="text-sm text-zinc-400">
          Generating BRD… this can take a minute or two.
        </p>
      )}
      {job?.status === "error" && (
        <p className="text-sm text-rose-400">Error: {job.error}</p>
      )}

      {summary && (
        <>
          <div className="flex flex-wrap gap-2 items-center text-xs mb-4">
            <span className={`px-2 py-0.5 rounded border ${ratingClass[summary.rating]}`}>
              {summary.rating.toUpperCase()}
            </span>
            <span className="text-zinc-500">v{summary.version}</span>
            <span className="text-zinc-500">{summary.attempts} attempt(s)</span>
            <span className="text-zinc-500">strategy: {summary.strategy}</span>
            <span className="text-zinc-500">
              score: {summary.weighted_score.toFixed(2)}
            </span>
          </div>

          <iframe
            title="BRD"
            src={`/api/repos/${encodeURIComponent(repoId)}/brd/${summary.id}/html`}
            sandbox="allow-same-origin"
            className="w-full h-[70vh] border border-zinc-800 rounded bg-white"
          />

          <button
            onClick={() => setShowFeedback((v) => !v)}
            className="mt-3 text-xs text-indigo-400 hover:text-indigo-300 underline"
          >
            {showFeedback ? "Hide" : "Show"} judge report ({summary.attempts} attempt(s))
          </button>
          {showFeedback && (
            <div className="mt-2 text-xs space-y-2">
              {summary.attempt_history.map((a) => (
                <div key={a.attempt} className="border border-zinc-800 rounded p-2 bg-zinc-950/50">
                  <div className="font-medium text-zinc-300">
                    Attempt {a.attempt} —{" "}
                    <span className={ratingClass[a.rating]?.split(" ").find((c) => c.startsWith("text-")) ?? ""}>
                      {a.rating}
                    </span>{" "}
                    (score {a.weighted_score.toFixed(2)})
                  </div>
                  {a.feedback.length === 0 ? (
                    <div className="text-zinc-500 mt-1">No feedback.</div>
                  ) : (
                    <ul className="list-disc pl-5 mt-1 text-zinc-400 space-y-1">
                      {a.feedback.map((f, i) => (
                        <li key={i}>
                          <strong className="text-zinc-300">
                            [{f.dimension}/{f.severity}]
                          </strong>{" "}
                          {f.target_section}: {f.suggestion}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
