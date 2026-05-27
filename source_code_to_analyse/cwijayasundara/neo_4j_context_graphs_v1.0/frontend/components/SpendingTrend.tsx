"use client";

import { Box, Heading, Text } from "@chakra-ui/react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { TrendPoint } from "@/lib/types";

interface Props {
  data: TrendPoint[] | undefined;
  isLoading: boolean;
}

export function SpendingTrend({ data, isLoading }: Props) {
  const chartData = data ?? [];

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
        Spending Trend
      </Heading>
      <Text fontSize="xs" color="gray.500" mb={4}>
        Monthly income vs. spending
      </Text>

      {chartData.length === 0 ? (
        <Text fontSize="sm" color="gray.400" textAlign="center" py={10}>
          No trend data available
        </Text>
      ) : (
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
            <XAxis dataKey="month" fontSize={12} tick={{ fill: "#718096" }} />
            <YAxis fontSize={12} tick={{ fill: "#718096" }} />
            <Tooltip
              contentStyle={{
                borderRadius: "8px",
                border: "1px solid #E2E8F0",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Line
              type="monotone"
              dataKey="total_in"
              name="Income"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="total_out"
              name="Spending"
              stroke="#ef4444"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Box>
  );
}
