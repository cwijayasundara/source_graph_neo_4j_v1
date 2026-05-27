"use client";

import { Box, SimpleGrid, Heading, Text, Flex, Spinner } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { fetchSummary, fetchTrends, fetchCategories, fetchMerchants } from "@/lib/api";
import { SummaryCards } from "./SummaryCards";
import { SpendingTrend } from "./SpendingTrend";
import { CategoryDonut } from "./CategoryDonut";
import { TopMerchants } from "./TopMerchants";
import { RecurringPayments } from "./RecurringPayments";

export function DashboardView() {
  const summaryQ = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => fetchSummary(),
  });

  const trendsQ = useQuery({
    queryKey: ["dashboard", "trends"],
    queryFn: () => fetchTrends(6),
  });

  const categoriesQ = useQuery({
    queryKey: ["dashboard", "categories"],
    queryFn: () => fetchCategories(),
  });

  const merchantsQ = useQuery({
    queryKey: ["merchants"],
    queryFn: () => fetchMerchants(100),
    select: (d) => d.merchants,
  });

  const anyError = summaryQ.error || trendsQ.error || categoriesQ.error || merchantsQ.error;

  return (
    <Box p={6} maxW="1400px" mx="auto">
      <Flex justify="space-between" align="center" mb={6}>
        <Box>
          <Heading size="lg">Dashboard</Heading>
          <Text fontSize="sm" color="gray.500">
            Financial overview and spending insights
          </Text>
        </Box>
        {(summaryQ.isFetching || trendsQ.isFetching) && (
          <Spinner size="sm" color="gray.400" />
        )}
      </Flex>

      {anyError && (
        <Box
          bg="red.50"
          borderRadius="md"
          p={4}
          mb={4}
          borderWidth="1px"
          borderColor="red.200"
        >
          <Text fontSize="sm" color="red.600">
            Unable to load dashboard data. Is the backend running?
          </Text>
        </Box>
      )}

      <SummaryCards summary={summaryQ.data} isLoading={summaryQ.isLoading} />

      <Box mt={4}>
        <SpendingTrend data={trendsQ.data} isLoading={trendsQ.isLoading} />
      </Box>

      <Box mt={4}>
        <CategoryDonut data={categoriesQ.data} isLoading={categoriesQ.isLoading} />
      </Box>

      <SimpleGrid columns={{ base: 1, lg: 2 }} gap={4} mt={4}>
        <TopMerchants merchants={merchantsQ.data} isLoading={merchantsQ.isLoading} />
        <RecurringPayments merchants={merchantsQ.data} isLoading={merchantsQ.isLoading} />
      </SimpleGrid>
    </Box>
  );
}
