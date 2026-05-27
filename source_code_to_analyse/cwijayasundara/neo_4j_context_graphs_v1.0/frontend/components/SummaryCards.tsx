"use client";

import { Box, Flex, Text, Heading, SimpleGrid } from "@chakra-ui/react";
import { TrendingUp, TrendingDown, Wallet } from "lucide-react";
import type { DashboardSummary } from "@/lib/types";

function fmt(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(Math.abs(value));
}

interface Props {
  summary: DashboardSummary | undefined;
  isLoading: boolean;
}

export function SummaryCards({ summary, isLoading }: Props) {
  const cards = [
    {
      label: "Money In",
      value: summary?.total_in ?? 0,
      color: "green.500",
      bg: "green.50",
      icon: TrendingUp,
    },
    {
      label: "Money Out",
      value: summary?.total_out ?? 0,
      color: "red.500",
      bg: "red.50",
      icon: TrendingDown,
    },
    {
      label: "Net",
      value: summary?.net ?? 0,
      color: (summary?.net ?? 0) >= 0 ? "green.500" : "red.500",
      bg: "gray.50",
      icon: Wallet,
    },
  ];

  return (
    <SimpleGrid columns={{ base: 1, sm: 3 }} gap={4}>
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Box
            key={card.label}
            bg="white"
            borderRadius="lg"
            borderWidth="1px"
            borderColor="gray.200"
            p={5}
            opacity={isLoading ? 0.6 : 1}
          >
            <Flex justify="space-between" align="center" mb={2}>
              <Text fontSize="sm" color="gray.500" fontWeight="medium">
                {card.label}
              </Text>
              <Flex
                w={8}
                h={8}
                align="center"
                justify="center"
                borderRadius="md"
                bg={card.bg}
              >
                <Icon size={16} color="currentColor" style={{ color: "var(--icon-color)" }} />
              </Flex>
            </Flex>
            <Heading size="lg" color={card.color}>
              {fmt(card.value)}
            </Heading>
            {card.label === "Net" && summary && (
              <Text fontSize="xs" color="gray.400" mt={1}>
                {summary.transaction_count} transactions
              </Text>
            )}
          </Box>
        );
      })}
    </SimpleGrid>
  );
}
