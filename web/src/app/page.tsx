"use client";

import { useEffect, useState } from "react";
import { api, Repo } from "@/lib/api";
import { AddRepoForm } from "@/components/AddRepoForm";
import { RepoCard } from "@/components/RepoCard";
import { StatsPanel } from "@/components/StatsPanel";
import { GitBranch } from "lucide-react";

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadRepos = async () => {
    try {
      setLoading(true);
      const data = await api.listRepos();
      setRepos(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load repos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const handleDelete = async (slug: string) => {
    await api.deleteRepo(slug);
    loadRepos();
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-3">
          <GitBranch className="w-6 h-6 text-indigo-400" />
          <h1 className="text-xl font-semibold">Code Context Graph</h1>
          <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
            v0.2
          </span>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <section>
          <h2 className="text-lg font-medium mb-4 text-zinc-300">
            Add a Repository
          </h2>
          <AddRepoForm onAdded={loadRepos} />
        </section>

        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        <section>
          <h2 className="text-lg font-medium mb-4 text-zinc-300">
            Repositories ({repos.length})
          </h2>
          {loading ? (
            <div className="text-zinc-500 text-sm">Loading...</div>
          ) : repos.length === 0 ? (
            <div className="text-zinc-500 text-sm border border-dashed border-zinc-700 rounded-lg p-8 text-center">
              No repositories ingested yet. Clone one from GitHub or add a local
              path above.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {repos.map((repo) => (
                <RepoCard
                  key={repo.slug}
                  repo={repo}
                  onDelete={() => handleDelete(repo.slug)}
                />
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="text-lg font-medium mb-4 text-zinc-300">
            Graph Statistics
          </h2>
          <StatsPanel />
        </section>
      </main>
    </div>
  );
}
