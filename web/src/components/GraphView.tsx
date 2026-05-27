"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, GraphData, GraphNode } from "@/lib/api";
import { kindColor, relColor } from "@/lib/colors";

interface Props {
  repo?: string;
  onNodeClick?: (node: GraphNode) => void;
}

export function GraphView({ repo, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [ForceGraph, setForceGraph] = useState<any>(null);

  useEffect(() => {
    import("react-force-graph-2d").then((mod) => {
      setForceGraph(() => mod.default);
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .getGraph(repo, 300)
      .then(setGraphData)
      .catch(() => setGraphData({ nodes: [], links: [] }))
      .finally(() => setLoading(false));
  }, [repo]);

  const handleNodeClick = useCallback(
    (node: any) => {
      if (onNodeClick && node.id) {
        onNodeClick(node as GraphNode);
      }
    },
    [onNodeClick]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500 text-sm">
        Loading graph...
      </div>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500 text-sm">
        No graph data available.
      </div>
    );
  }

  if (!ForceGraph) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500 text-sm">
        Loading visualization...
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full h-[600px] bg-zinc-950 rounded-lg border border-zinc-800 overflow-hidden relative">
      <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-2">
        {Object.entries(
          graphData.nodes.reduce<Record<string, number>>((acc, n) => {
            acc[n.kind] = (acc[n.kind] || 0) + 1;
            return acc;
          }, {})
        ).map(([kind, count]) => (
          <span
            key={kind}
            className="flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-zinc-900/80 backdrop-blur border border-zinc-800"
          >
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: kindColor(kind) }}
            />
            {kind} ({count})
          </span>
        ))}
      </div>

      <ForceGraph
        graphData={graphData}
        width={containerRef.current?.clientWidth || 800}
        height={600}
        backgroundColor="#09090b"
        nodeLabel={(node: any) =>
          `${node.name} (${node.kind})${node.signature ? "\n" + node.signature : ""}`
        }
        nodeColor={(node: any) => kindColor(node.kind)}
        nodeRelSize={5}
        nodeVal={(node: any) => {
          const sizes: Record<string, number> = {
            Module: 4,
            Class: 3,
            Enum: 3,
            Function: 2,
            Method: 1.5,
            Constant: 1,
            GlobalVar: 1,
            External: 1,
          };
          return sizes[node.kind] ?? 1;
        }}
        linkColor={(link: any) => relColor(link.type)}
        linkWidth={0.5}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkLabel={(link: any) => link.type}
        onNodeClick={handleNodeClick}
        cooldownTicks={100}
        nodeCanvasObjectMode={() => "after" as const}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D) => {
          const label = node.name;
          const fontSize = 10;
          ctx.font = `${fontSize}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "rgba(255, 255, 255, 0.7)";
          ctx.fillText(label, node.x, node.y + 10);
        }}
      />
    </div>
  );
}
