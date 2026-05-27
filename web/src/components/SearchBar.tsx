"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Search, Loader2 } from "lucide-react";
import { kindColor } from "@/lib/colors";

interface Props {
  onSelect?: (qname: string) => void;
}

export function SearchBar({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.search(query.trim());
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities, functions, classes..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-md pl-10 pr-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-3 py-2 rounded-md text-sm transition"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Search className="w-4 h-4" />
          )}
        </button>
      </form>

      {results && results.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg divide-y divide-zinc-800 max-h-64 overflow-y-auto">
          {results.map((r, i) => (
            <button
              key={i}
              onClick={() => onSelect?.(r.name as string)}
              className="w-full flex items-center gap-3 px-3 py-2 hover:bg-zinc-800/50 text-left transition"
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  backgroundColor: kindColor(r.kind as string),
                }}
              />
              <div className="min-w-0">
                <div className="text-sm text-zinc-200 truncate">
                  {r.name as string}
                </div>
                <div className="text-xs text-zinc-500 truncate">
                  {r.kind as string} &middot; {r.file as string}
                </div>
              </div>
              <span className="ml-auto text-xs text-zinc-600 font-mono shrink-0">
                {(r.score as number)?.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      )}

      {results && results.length === 0 && (
        <p className="text-zinc-500 text-sm">No results found.</p>
      )}
    </div>
  );
}
