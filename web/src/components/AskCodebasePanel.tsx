"use client";

import { FormEvent, useState } from "react";
import { api, AskResult } from "@/lib/api";
import { Bot, Loader2, Send } from "lucide-react";

interface Props {
  repo: string;
}

export function AskCodebasePanel({ repo }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    try {
      const response = await api.askCodebase(repo, trimmed);
      setResult(response);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ask failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Bot className="w-4 h-4 text-indigo-400" />
        <h3 className="text-sm font-medium text-zinc-300">Ask the Codebase</h3>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-wrap gap-3">
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Which routes touch Neo4j?"
          className="flex-1 min-w-[260px] bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:text-zinc-400 px-4 py-2 rounded-md text-sm font-medium transition"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
          Ask
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {result && (
        <div className="space-y-4">
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-sm text-zinc-200 whitespace-pre-wrap">{result.answer}</p>
          </div>

          <details className="rounded-md border border-zinc-800 bg-zinc-950">
            <summary className="cursor-pointer px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200">
              Generated Cypher
            </summary>
            <pre className="border-t border-zinc-800 p-4 text-xs text-zinc-300 overflow-x-auto">
              {result.cypher}
            </pre>
          </details>

          {result.rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    {Object.keys(result.rows[0]).map((column) => (
                      <th
                        key={column}
                        className="text-left text-zinc-400 font-medium py-2 px-3"
                      >
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr
                      key={index}
                      className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                    >
                      {Object.values(row).map((value, valueIndex) => (
                        <td
                          key={valueIndex}
                          className="py-1.5 px-3 text-zinc-300 font-mono text-xs"
                        >
                          {Array.isArray(value)
                            ? value.join(" -> ")
                            : String(value ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
