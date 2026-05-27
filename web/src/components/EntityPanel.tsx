"use client";

import { useEffect, useState } from "react";
import { api, EntityDetail } from "@/lib/api";
import { kindColor, relColor } from "@/lib/colors";
import { ArrowDownLeft, ArrowUpRight, X } from "lucide-react";

interface Props {
  qname: string;
  onClose: () => void;
}

export function EntityPanel({ qname, onClose }: Props) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .getEntity(qname)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [qname]);

  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <div className="text-zinc-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <div className="text-zinc-500 text-sm">Entity not found.</div>
      </div>
    );
  }

  const e = detail.entity;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: kindColor(e.kind as string) }}
          />
          <span className="text-sm font-medium">{e.simple_name as string}</span>
          <span className="text-xs text-zinc-500">{e.kind as string}</span>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-4 max-h-[500px] overflow-y-auto">
        <div className="space-y-1.5 text-xs">
          <Row label="Qualified Name" value={e.qualified_name as string} />
          <Row label="File" value={e.file_path as string} />
          <Row
            label="Lines"
            value={`${e.start_line}–${e.end_line}`}
          />
          {e.signature ? <Row label="Signature" value={e.signature as string} mono /> : null}
          {e.complexity ? (
            <Row label="Complexity" value={String(e.complexity)} />
          ) : null}
          {e.is_async ? <Row label="Async" value="Yes" /> : null}
          {e.docstring ? (
            <div>
              <span className="text-zinc-500">Docstring:</span>
              <p className="mt-1 text-zinc-300 bg-zinc-800 rounded p-2 font-mono text-xs whitespace-pre-wrap">
                {e.docstring as string}
              </p>
            </div>
          ) : null}
          {e.semantic_summary ? (
            <Row label="Summary" value={e.semantic_summary as string} />
          ) : null}
          {e.semantic_layer ? (
            <Row label="Layer" value={e.semantic_layer as string} />
          ) : null}
        </div>

        {detail.incoming.length > 0 && (
          <div>
            <h4 className="text-xs text-zinc-400 font-medium mb-2 flex items-center gap-1">
              <ArrowDownLeft className="w-3 h-3" />
              Incoming ({detail.incoming.length})
            </h4>
            <div className="space-y-1">
              {detail.incoming.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{
                      backgroundColor: relColor(r.relationship) + "20",
                      color: relColor(r.relationship),
                    }}
                  >
                    {r.relationship}
                  </span>
                  <span className="text-zinc-300 truncate">{r.source}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {detail.outgoing.length > 0 && (
          <div>
            <h4 className="text-xs text-zinc-400 font-medium mb-2 flex items-center gap-1">
              <ArrowUpRight className="w-3 h-3" />
              Outgoing ({detail.outgoing.length})
            </h4>
            <div className="space-y-1">
              {detail.outgoing.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{
                      backgroundColor: relColor(r.relationship) + "20",
                      color: relColor(r.relationship),
                    }}
                  >
                    {r.relationship}
                  </span>
                  <span className="text-zinc-300 truncate">{r.target}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <span className="text-zinc-500 shrink-0">{label}:</span>
      <span className={`text-zinc-300 break-all ${mono ? "font-mono" : ""}`}>
        {value}
      </span>
    </div>
  );
}
