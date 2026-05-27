"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { kindColor, relColor } from "@/lib/colors";

interface Stats {
  entity_counts: { kind: string; count: number }[];
  relationship_counts: { rel_type: string; count: number }[];
}

export function StatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
  }, []);

  if (!stats) return <div className="text-zinc-500 text-sm">Loading stats...</div>;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">
          Entities by Kind
        </h3>
        <div className="space-y-2">
          {stats.entity_counts.map((row) => (
            <div key={row.kind} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: kindColor(row.kind) }}
                />
                <span className="text-sm">{row.kind}</span>
              </div>
              <span className="text-sm text-zinc-400 font-mono">
                {row.count}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">
          Relationships by Type
        </h3>
        <div className="space-y-2">
          {stats.relationship_counts.map((row) => (
            <div key={row.rel_type} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: relColor(row.rel_type) }}
                />
                <span className="text-sm">{row.rel_type}</span>
              </div>
              <span className="text-sm text-zinc-400 font-mono">
                {row.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
