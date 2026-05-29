"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { kindColor } from "@/lib/colors";
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

type Suggestion = { qualified_name: string; simple_name: string; kind: string };

interface Props {
  repo?: string;
}

export function QueryPanel({ repo }: Props) {
  const [kind, setKind] = useState("callers");
  const [name, setName] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const justSelected = useRef(false);

  const selected = QUERY_TYPES.find((q) => q.value === kind)!;
  // "complex" takes a number (min complexity), not an entity name — no suggestions.
  const suggestEnabled = kind !== "complex";

  // Debounced, repo-scoped suggestions as the user types. The cancelled flag
  // ignores out-of-order responses; cleanup clears the pending timer each keystroke.
  useEffect(() => {
    if (justSelected.current) {
      justSelected.current = false;
      return;
    }
    const term = name.trim();
    if (!suggestEnabled || term.length < 2) {
      setSuggestions([]);
      setShowSuggest(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const data = await api.suggest(term, repo);
        if (!cancelled) {
          setSuggestions(data);
          setShowSuggest(data.length > 0);
          setActiveIndex(-1);
        }
      } catch {
        if (!cancelled) {
          setSuggestions([]);
          setShowSuggest(false);
        }
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [name, repo, suggestEnabled]);

  const selectSuggestion = (s: Suggestion) => {
    justSelected.current = true;
    setName(s.qualified_name);
    setShowSuggest(false);
    setSuggestions([]);
    setActiveIndex(-1);
  };

  const onNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggest || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? -1 : i - 1));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      // Selecting from the dropdown; do not submit the query.
      e.preventDefault();
      selectSuggestion(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setShowSuggest(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setShowSuggest(false);
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

        <div className="relative flex-1 min-w-[200px]">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={onNameKeyDown}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggest(true);
            }}
            // Delay so a click on a suggestion registers before the list is hidden.
            onBlur={() => setTimeout(() => setShowSuggest(false), 120)}
            placeholder={selected.placeholder}
            autoComplete="off"
            className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {showSuggest && suggestions.length > 0 && (
            <div className="absolute z-20 mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-md shadow-lg divide-y divide-zinc-800 max-h-64 overflow-y-auto">
              {suggestions.map((s, i) => (
                <button
                  key={s.qualified_name}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => selectSuggestion(s)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-left transition ${
                    i === activeIndex ? "bg-zinc-800" : "hover:bg-zinc-800/50"
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: kindColor(s.kind) }}
                  />
                  <span className="text-sm text-zinc-200 truncate">{s.qualified_name}</span>
                  <span className="ml-auto text-xs text-zinc-500 shrink-0">{s.kind}</span>
                </button>
              ))}
            </div>
          )}
        </div>

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
