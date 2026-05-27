"use client";

import { useState, useCallback } from "react";
import { Box, Flex, SimpleGrid, Button, HStack, Text } from "@chakra-ui/react";
import { ChatInterface } from "@/components/ChatInterface";
import { ContextGraphView } from "@/components/ContextGraphView";
import { DecisionTracePanel } from "@/components/DecisionTracePanel";
import { Network, ListTree } from "lucide-react";
import type { GraphData } from "@/lib/config";

export default function InsightsPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [rightPanel, setRightPanel] = useState<"graph" | "traces">("graph");

  const handleGraphUpdate = useCallback((data: GraphData) => {
    setGraphData(data);
    setRightPanel("graph");
  }, []);

  return (
    <SimpleGrid columns={{ base: 1, lg: 2 }} h="calc(100dvh - 56px)">
      <Box borderRight={{ lg: "1px solid" }} borderColor="gray.200" overflow="hidden">
        <ChatInterface onGraphUpdate={handleGraphUpdate} />
      </Box>
      <Flex direction="column" overflow="hidden" display={{ base: "none", lg: "flex" }}>
        <HStack px={4} py={2} borderBottom="1px solid" borderColor="gray.200" gap={2}>
          <Button
            size="xs"
            variant={rightPanel === "graph" ? "solid" : "outline"}
            onClick={() => setRightPanel("graph")}
          >
            <Network size={12} />
            Graph
          </Button>
          <Button
            size="xs"
            variant={rightPanel === "traces" ? "solid" : "outline"}
            onClick={() => setRightPanel("traces")}
          >
            <ListTree size={12} />
            Traces
          </Button>
          {rightPanel === "graph" && !graphData && (
            <Text fontSize="xs" color="gray.400" ml={2}>
              Ask a question to see the relevant graph context
            </Text>
          )}
        </HStack>
        <Box flex={1} overflow="hidden">
          {rightPanel === "graph" ? (
            graphData ? (
              <ContextGraphView externalGraphData={graphData} subtitle="Relevant AI graph context" />
            ) : (
              <Flex h="100%" align="center" justify="center" direction="column" gap={2} p={8}>
                <Text color="gray.500" fontWeight="medium">No graph context yet</Text>
                <Text color="gray.400" fontSize="sm" textAlign="center" maxW="320px">
                  Ask a question to populate this panel with the graph context used by the assistant.
                </Text>
              </Flex>
            )
          ) : (
            <DecisionTracePanel />
          )}
        </Box>
      </Flex>
    </SimpleGrid>
  );
}
