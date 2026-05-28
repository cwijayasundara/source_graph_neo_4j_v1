"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, GraphNode, Repo } from "@/lib/api";
import { GraphView } from "@/components/GraphView";
import { QueryPanel } from "@/components/QueryPanel";
import { AskCodebasePanel } from "@/components/AskCodebasePanel";
import { SearchBar } from "@/components/SearchBar";
import { EntityPanel } from "@/components/EntityPanel";
import BRDPanel from "@/components/BRDPanel";
import { ArrowLeft, Box, FileText, GitBranch, Network, Users } from "lucide-react";

export default function RepoPage() {
  const params = useParams();
  const slug = Array.isArray(params.slug)
    ? params.slug.join("/")
    : (params.slug as string);

  const [repo, setRepo] = useState<Repo | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    api
      .getRepo(slug)
      .then(setRepo)
      .catch((e) => setError(e.message));
  }, [slug]);

  const handleNodeClick = (node: GraphNode) => {
    setSelectedEntity(node.id);
  };

  const handleSearchSelect = (qname: string) => {
    setSelectedEntity(qname);
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center gap-4">
          <Link href="/" className="text-zinc-400 hover:text-zinc-200 transition">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <GitBranch className="w-5 h-5 text-indigo-400" />
          <h1 className="text-lg font-semibold">{slug}</h1>

          {repo && (
            <div className="ml-auto flex items-center gap-4 text-xs text-zinc-400">
              <span className="flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" /> {repo.files_parsed} files
              </span>
              <span className="flex items-center gap-1">
                <Box className="w-3.5 h-3.5" /> {repo.entities} entities
              </span>
              <span className="flex items-center gap-1">
                <Network className="w-3.5 h-3.5" /> {repo.relationships} rels
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-3.5 h-3.5" /> {repo.authors} authors
              </span>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <SearchBar onSelect={handleSearchSelect} />
            <GraphView repo={slug} onNodeClick={handleNodeClick} />
          </div>

          <div className="space-y-4">
            {selectedEntity ? (
              <EntityPanel
                qname={selectedEntity}
                onClose={() => setSelectedEntity(null)}
              />
            ) : (
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 text-center text-zinc-500 text-sm">
                Click a node in the graph or search to inspect an entity.
              </div>
            )}
          </div>
        </div>

        <AskCodebasePanel repo={slug} />
        <QueryPanel repo={slug} />
        <BRDPanel repoId={slug} />
      </main>
    </div>
  );
}
