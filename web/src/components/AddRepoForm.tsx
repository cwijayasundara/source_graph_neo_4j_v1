"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Download, FolderOpen, Loader2 } from "lucide-react";

interface Props {
  onAdded: () => void;
}

export function AddRepoForm({ onAdded }: Props) {
  const [mode, setMode] = useState<"github" | "local">("github");
  const [url, setUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [branch, setBranch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "github") {
        await api.cloneRepo(url, branch || undefined);
      } else {
        await api.ingestLocal(localPath);
      }
      setUrl("");
      setLocalPath("");
      setBranch("");
      onAdded();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to ingest");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4"
    >
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setMode("github")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition ${
            mode === "github"
              ? "bg-indigo-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Download className="w-4 h-4" />
          GitHub URL
        </button>
        <button
          type="button"
          onClick={() => setMode("local")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition ${
            mode === "local"
              ? "bg-indigo-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <FolderOpen className="w-4 h-4" />
          Local Path
        </button>
      </div>

      {mode === "github" ? (
        <div className="flex gap-3">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            required
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="branch (optional)"
            className="w-40 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
      ) : (
        <input
          type="text"
          value={localPath}
          onChange={(e) => setLocalPath(e.target.value)}
          placeholder="/path/to/local/repo"
          required
          className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:text-zinc-400 px-4 py-2 rounded-md text-sm font-medium transition"
      >
        {loading && <Loader2 className="w-4 h-4 animate-spin" />}
        {loading ? "Ingesting..." : "Clone & Ingest"}
      </button>
    </form>
  );
}
