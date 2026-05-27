"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Play, Loader2 } from "lucide-react";

const QUERY_TYPES = [
  { value: "callers", label: "What calls this?", placeholder: "function name" },
  { value: "calls", label: "What does it call?", placeholder: "function name" },
  { value: "impact", label: "Impact analysis", placeholder: "entity name" },
  { value: "hierarchy", label: "Class hierarchy", placeholder: "class name" },
  { value: "imports", label: "Module dependencies", placeholder: "module name" },
  { value: "importers", label: "Who imports this?", placeholder: "module name" },
  { value: "path", label: "Full call path", placeholder: "entry point name" },
  { value: "cochange", label: "Co-changed files", placeholder: "module name" },
  { value: "owners", label: "File owners", placeholder: "file path" },
  { value: "complex", label: "Complex functions", placeholder: "min complexity" },
];

interface Props {
  repo?: string;
}

export function QueryPanel({ repo }: Props) {
  const [kind, setKind] = useState("callers");
  const [name, setName] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = QUERY_TYPES.find((q) => q.value === kind)!;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const minComplexity = kind === "complex" ? Number.parseInt(name.trim(), 10) || 5 : 5;
      const queryName = kind === "complex" ? "" : name.trim();
      const res = await api.runQuery(kind, queryName, 3, minComplexity, repo);
      setResults(res.results);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Query failed");
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-300">Query the Graph</h3>

      <form onSubmit={handleSubmit} className="flex flex-wrap gap-3">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {QUERY_TYPES.map((q) => (
            <option key={q.value} value={q.value}>
              {q.label}
            </option>
          ))}
        </select>

        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={selected.placeholder}
          className="flex-1 min-w-[200px] bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />

        <button
          type="submit"
          disabled={loading || !name.trim()}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:text-zinc-400 px-4 py-2 rounded-md text-sm font-medium transition"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          Run
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {results && (
        <div className="overflow-x-auto">
          {results.length === 0 ? (
            <p className="text-zinc-500 text-sm">No results found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {Object.keys(results[0]).map((col) => (
                    <th
                      key={col}
                      className="text-left text-zinc-400 font-medium py-2 px-3"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                  >
                    {Object.values(row).map((val, j) => (
                      <td key={j} className="py-1.5 px-3 text-zinc-300 font-mono text-xs">
                        {Array.isArray(val)
                          ? val.join(" -> ")
                          : String(val ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
