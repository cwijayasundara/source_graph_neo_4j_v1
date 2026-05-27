"use client";

import { Box, Heading, Text, Table, Badge } from "@chakra-ui/react";
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

export function RecurringPayments({ merchants, isLoading }: Props) {
  // Merchants with 3+ transactions are considered "recurring"
  const recurring = (merchants ?? []).filter(
    (m) => m.transaction_count >= 3,
  );

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
        Recurring Payments
      </Heading>
      <Text fontSize="xs" color="gray.500" mb={4}>
        Merchants with 3+ monthly appearances
      </Text>

      {recurring.length === 0 ? (
        <Text fontSize="sm" color="gray.400" textAlign="center" py={6}>
          No recurring payments detected
        </Text>
      ) : (
        <Box overflowY="auto" maxH="400px" overflowX="auto">
          <Table.Root size="sm" variant="outline">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeader>Merchant</Table.ColumnHeader>
                <Table.ColumnHeader>Category</Table.ColumnHeader>
                <Table.ColumnHeader textAlign="right">Frequency</Table.ColumnHeader>
                <Table.ColumnHeader textAlign="right">Total</Table.ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {recurring.map((m) => (
                <Table.Row key={m.merchant}>
                  <Table.Cell fontWeight="medium" fontSize="sm">
                    {m.merchant}
                  </Table.Cell>
                  <Table.Cell fontSize="sm">
                    <Badge size="sm" variant="subtle">
                      {m.category}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell textAlign="right" fontSize="sm">
                    {m.transaction_count}x
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
