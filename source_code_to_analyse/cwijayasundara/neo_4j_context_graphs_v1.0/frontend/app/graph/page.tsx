"use client";

import { useEffect, useState } from "react";
import { Box, Button, Flex, Spinner, Text, VStack, HStack } from "@chakra-ui/react";
import dynamic from "next/dynamic";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { GRAPH_PRESETS } from "@/lib/config";
import type { GraphData, GraphPresetId } from "@/lib/config";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(/\/api\/?$/, "");

const ContextGraphView = dynamic(
  () =>
    import("@/components/ContextGraphView").then((mod) => mod.ContextGraphView),
  {
    ssr: false,
    loading: () => (
      <Flex align="center" justify="center" h="100%" color="gray.400">
        <Spinner size="lg" />
      </Flex>
    ),
  },
);

interface OverviewStats {
  nodes: number;
  relationships: number;
  merchants: number;
  categories: number;
  accounts: number;
  people: number;
  statements: number;
  transactions: number;
}

function graphRecords(data: GraphData): Record<string, unknown>[] {
  if (data.results?.length) return data.results;
  if (data.nodes?.length || data.relationships?.length) {
    return [...(data.nodes || []), ...(data.relationships || [])];
  }
  return [];
}

export default function GraphPage() {
  const [selectedPreset, setSelectedPreset] = useState<GraphPresetId>("overview");
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);

  const selectedPresetLabel =
    GRAPH_PRESETS.find((preset) => preset.id === selectedPreset)?.label || "Graph";

  useEffect(() => {
    async function loadFinanceGraph() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_URL}/api/graph/story?preset=${selectedPreset}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json() as GraphData;
        const records = graphRecords(data);
        if (records.length) {
          setGraphData(data);
          const nodes = records.filter((r: Record<string, unknown>) => Array.isArray(r.labels));
          const countLabel = (label: string) =>
            nodes.filter((n: Record<string, unknown>) => (n.labels as string[]).includes(label)).length;
          setStats({
            nodes: data.stats?.nodes ?? nodes.length,
            relationships: data.stats?.relationships ?? records.length - nodes.length,
            merchants: countLabel("Merchant"),
            categories: countLabel("Category"),
            accounts: countLabel("Account"),
            people: countLabel("Person"),
            statements: countLabel("Statement"),
            transactions: countLabel("Transaction"),
          });
        } else {
          setGraphData(null);
          setStats(null);
          setError(`${selectedPresetLabel} has no graph data. Try Explore All or run 'make ingest'.`);
        }
      } catch (err) {
        setGraphData(null);
        setStats(null);
        setError(`Failed to load ${selectedPresetLabel}: ${err instanceof Error ? err.message : "Unknown error"}`);
      } finally {
        setLoading(false);
      }
    }
    loadFinanceGraph();
  }, [selectedPreset, selectedPresetLabel]);

  if (loading) {
    return (
      <Flex align="center" justify="center" h="calc(100dvh - 56px)" direction="column" gap={2}>
        <Spinner size="lg" />
        <Text fontSize="sm" color="gray.500">Loading financial data graph...</Text>
      </Flex>
    );
  }

  return (
    <Flex h="calc(100dvh - 56px)" bg="gray.50">
      <VStack
        as="nav"
        w="172px"
        flexShrink={0}
        align="stretch"
        gap={1}
        p={3}
        bg="white"
        borderRightWidth="1px"
        borderColor="gray.200"
      >
        <Text fontSize="xs" fontWeight="bold" color="gray.500" textTransform="uppercase">
          Story
        </Text>
        {GRAPH_PRESETS.map((preset) => (
          <Button
            key={preset.id}
            size="sm"
            justifyContent="flex-start"
            variant={selectedPreset === preset.id ? "solid" : "ghost"}
            colorPalette={selectedPreset === preset.id ? "blue" : "gray"}
            onClick={() => setSelectedPreset(preset.id)}
          >
            {preset.label}
          </Button>
        ))}
      </VStack>

      <Box flex="1" minW={0} position="relative" bg="white">
        {stats && (
        <HStack
          position="absolute"
          top={2}
          left={2}
          zIndex={10}
          bg="white"
          borderRadius="md"
          borderWidth="1px"
          borderColor="gray.200"
          px={3}
          py={2}
          gap={3}
          shadow="sm"
        >
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">Nodes</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.nodes}</Text>
          </VStack>
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">Edges</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.relationships}</Text>
          </VStack>
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">Merchants</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.merchants}</Text>
          </VStack>
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">Categories</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.categories}</Text>
          </VStack>
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">Accounts</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.accounts}</Text>
          </VStack>
          <VStack gap={0}>
            <Text fontSize="xs" color="gray.500">People</Text>
            <Text fontSize="sm" fontWeight="bold">{stats.people}</Text>
          </VStack>
        </HStack>
      )}

        {error ? (
          <Flex align="center" justify="center" h="100%" direction="column" gap={3}>
            <Text color="red.500">{error}</Text>
            {selectedPreset !== "explore-all" && (
              <Button size="sm" onClick={() => setSelectedPreset("explore-all")}>
                Explore All
              </Button>
            )}
          </Flex>
        ) : (
          <ErrorBoundary fallbackMessage="Graph visualization error">
            {graphData && (
              <ContextGraphView
                externalGraphData={graphData}
                subtitle={`${selectedPresetLabel} graph story`}
                onAskAbout={() => {}}
              />
            )}
          </ErrorBoundary>
        )}
      </Box>
    </Flex>
  );
}
