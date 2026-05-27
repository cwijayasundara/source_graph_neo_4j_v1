"use client";

import { Box, Flex, Heading, Text, VStack, Badge, IconButton } from "@chakra-ui/react";
import { X } from "lucide-react";
import type { Transaction } from "@/lib/types";

function fmt(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(value);
}

interface Props {
  transaction: Transaction;
  onClose: () => void;
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <Box>
      <Text fontSize="xs" color="gray.500" fontWeight="medium">
        {label}
      </Text>
      <Text fontSize="sm">{value ?? "—"}</Text>
    </Box>
  );
}

export function TransactionDetail({ transaction: tx, onClose }: Props) {
  const isIncome = tx.amount > 0;

  return (
    <Box
      position="fixed"
      top={0}
      right={0}
      h="100dvh"
      w={{ base: "100%", md: "400px" }}
      bg="white"
      borderLeft="1px solid"
      borderColor="gray.200"
      boxShadow="xl"
      zIndex={30}
      overflow="auto"
    >
      <Flex
        px={5}
        py={4}
        borderBottom="1px solid"
        borderColor="gray.200"
        justify="space-between"
        align="center"
      >
        <Heading size="sm">Transaction Detail</Heading>
        <IconButton
          aria-label="Close detail"
          variant="ghost"
          size="sm"
          onClick={onClose}
        >
          <X size={16} />
        </IconButton>
      </Flex>

      <VStack align="stretch" gap={4} px={5} py={5}>
        {/* Amount card */}
        <Box
          bg={isIncome ? "green.50" : "red.50"}
          borderRadius="lg"
          p={4}
          textAlign="center"
        >
          <Text fontSize="xs" color="gray.500" mb={1}>
            Amount
          </Text>
          <Heading size="xl" color={isIncome ? "green.600" : "red.600"}>
            {isIncome ? "+" : ""}{fmt(tx.amount)}
          </Heading>
        </Box>

        <Field label="Date" value={tx.date} />
        <Field label="Description" value={tx.description} />
        <Field label="Merchant" value={tx.merchant} />

        <Box>
          <Text fontSize="xs" color="gray.500" fontWeight="medium" mb={1}>
            Category
          </Text>
          <Badge size="sm" variant="subtle">
            {tx.category}
          </Badge>
        </Box>

        <Field label="Payment Method" value={tx.payment_method} />
        <Field label="Account" value={tx.account_id} />

        {tx.person && <Field label="Paid To" value={tx.person} />}

        <Field label="Transaction ID" value={tx.id} />
      </VStack>
    </Box>
  );
}
