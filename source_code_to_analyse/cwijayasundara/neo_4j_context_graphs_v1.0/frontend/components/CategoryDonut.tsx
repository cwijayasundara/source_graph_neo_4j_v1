"use client";

import { Box, Heading, Text, Flex } from "@chakra-ui/react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from "recharts";
import type { CategoryBreakdown } from "@/lib/types";

const COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#ec4899",
  "#f97316",
  "#14b8a6",
];

const MAX_SLICES = 8;

interface Props {
  data: CategoryBreakdown[] | undefined;
  isLoading: boolean;
}

function formatGBP(value: number) {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function CategoryDonut({ data, isLoading }: Props) {
  const sorted = (data ?? [])
    .map((d) => ({ ...d, value: Math.abs(d.total) }))
    .sort((a, b) => b.value - a.value);

  const top = sorted.slice(0, MAX_SLICES);
  const rest = sorted.slice(MAX_SLICES);

  const chartData =
    rest.length > 0
      ? [
          ...top,
          {
            category: "Other",
            value: rest.reduce((sum, d) => sum + d.value, 0),
            percentage: rest.reduce((sum, d) => sum + (d.percentage ?? 0), 0),
            total: rest.reduce((sum, d) => sum + d.total, 0),
            transaction_count: rest.reduce(
              (sum, d) => sum + d.transaction_count,
              0
            ),
            top_merchant: null,
          },
        ]
      : top;

  const grandTotal = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <Box
      bg="white"
      borderRadius="lg"
      borderWidth="1px"
      borderColor="gray.200"
      p={5}
      opacity={isLoading ? 0.6 : 1}
    >
      <Heading size="sm" mb={1}>
        Spending by Category
      </Heading>
      <Text fontSize="xs" color="gray.500" mb={4}>
        Top {MAX_SLICES} categories
      </Text>

      {chartData.length === 0 ? (
        <Text fontSize="sm" color="gray.400" textAlign="center" py={10}>
          No category data available
        </Text>
      ) : (
        <Flex direction={{ base: "column", md: "row" }} align="center" gap={4}>
          <Box flex="0 0 280px">
            <ResponsiveContainer width={280} height={280}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={120}
                  paddingAngle={2}
                >
                  {chartData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => formatGBP(Number(value))}
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #E2E8F0",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </Box>

          <Box flex="1" minW="0">
            {chartData.map((item, index) => {
              const pct =
                grandTotal > 0
                  ? ((item.value / grandTotal) * 100).toFixed(1)
                  : "0";
              return (
                <Flex
                  key={item.category}
                  align="center"
                  py={1.5}
                  borderBottomWidth={
                    index < chartData.length - 1 ? "1px" : "0"
                  }
                  borderColor="gray.100"
                  gap={3}
                >
                  <Box
                    w={3}
                    h={3}
                    borderRadius="sm"
                    flexShrink={0}
                    bg={COLORS[index % COLORS.length]}
                  />
                  <Text fontSize="sm" flex="1" lineClamp={1}>
                    {item.category}
                  </Text>
                  <Text fontSize="sm" fontWeight="medium" whiteSpace="nowrap">
                    {formatGBP(item.value)}
                  </Text>
                  <Text
                    fontSize="xs"
                    color="gray.500"
                    w="50px"
                    textAlign="right"
                  >
                    {pct}%
                  </Text>
                </Flex>
              );
            })}
          </Box>
        </Flex>
      )}
    </Box>
  );
}
