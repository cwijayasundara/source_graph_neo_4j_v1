"use client";

import Link from "next/link";
import { Repo } from "@/lib/api";
import { Box, FileText, GitFork, Network, Trash2, Users } from "lucide-react";

interface Props {
  repo: Repo;
  onDelete: () => void;
}

export function RepoCard({ repo, onDelete }: Props) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition group">
      <div className="flex items-start justify-between mb-3">
        <Link
          href={`/repo/${repo.slug}`}
          className="text-indigo-400 hover:text-indigo-300 font-medium text-sm"
        >
          {repo.slug}
        </Link>
        <button
          onClick={(e) => {
            e.preventDefault();
            if (confirm(`Delete ${repo.slug}?`)) onDelete();
          }}
          className="text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-zinc-400">
        <div className="flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5" />
          {repo.files_parsed} files
        </div>
        <div className="flex items-center gap-1.5">
          <Box className="w-3.5 h-3.5" />
          {repo.entities} entities
        </div>
        <div className="flex items-center gap-1.5">
          <Network className="w-3.5 h-3.5" />
          {repo.relationships} rels
        </div>
        <div className="flex items-center gap-1.5">
          <Users className="w-3.5 h-3.5" />
          {repo.authors} authors
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-zinc-800">
        <Link
          href={`/repo/${repo.slug}`}
          className="text-xs text-zinc-500 hover:text-indigo-400 transition"
        >
          Explore graph &rarr;
        </Link>
      </div>
    </div>
  );
}
