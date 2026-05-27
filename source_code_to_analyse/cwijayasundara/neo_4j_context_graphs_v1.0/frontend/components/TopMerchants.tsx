"use client";

import { Box, Heading, Text, Table } from "@chakra-ui/react";
import type { Merchant } from "@/lib/types";

function fmt(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(value);
}

interface Props {
  merchants: Merchant[] | undefined;
  isLoading: boolean;
}

export function TopMerchants({ merchants, isLoading }: Props) {
  const top10 = (merchants ?? []).slice(0, 10);

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
        Top Merchants
      </Heading>
      <Text fontSize="xs" color="gray.500" mb={4}>
        By total spend
      </Text>

      {top10.length === 0 ? (
        <Text fontSize="sm" color="gray.400" textAlign="center" py={6}>
          No merchant data available
        </Text>
      ) : (
        <Box overflowX="auto">
          <Table.Root size="sm" variant="outline">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeader>Merchant</Table.ColumnHeader>
                <Table.ColumnHeader>Category</Table.ColumnHeader>
                <Table.ColumnHeader textAlign="right">Transactions</Table.ColumnHeader>
                <Table.ColumnHeader textAlign="right">Total Spent</Table.ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {top10.map((m) => (
                <Table.Row key={m.merchant}>
                  <Table.Cell fontWeight="medium" fontSize="sm">
                    {m.merchant}
                  </Table.Cell>
                  <Table.Cell fontSize="sm" color="gray.600">
                    {m.category}
                  </Table.Cell>
                  <Table.Cell textAlign="right" fontSize="sm">
                    {m.transaction_count}
                  </Table.Cell>
                  <Table.Cell textAlign="right" fontSize="sm" fontWeight="medium">
                    {fmt(m.total_spent)}
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        </Box>
      )}
    </Box>
  );
}
