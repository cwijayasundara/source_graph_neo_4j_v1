"use client";

import { useState, useCallback } from "react";
import {
  Box,
  Flex,
  Heading,
  Text,
  Input,
  Button,
  HStack,
  Table,
  Badge,
  Spinner,
} from "@chakra-ui/react";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchTransactions, fetchCategories, searchTransactions } from "@/lib/api";
import { TransactionDetail } from "./TransactionDetail";
import type { Transaction } from "@/lib/types";

function fmt(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(Math.abs(value));
}

export function TransactionExplorer() {
  const [page, setPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);

  const perPage = 30;

  // Fetch categories for filter options
  const categoriesQ = useQuery({
    queryKey: ["categories-list"],
    queryFn: () => fetchCategories(),
    select: (cats) => cats.map((c) => c.category),
  });

  // Main transaction list (paginated)
  const txQ = useQuery({
    queryKey: ["transactions", page, perPage, categoryFilter],
    queryFn: () =>
      fetchTransactions({
        page,
        per_page: perPage,
        category: categoryFilter || undefined,
        sort_by: "date",
        sort_order: "desc",
      }),
    enabled: !activeSearch,
  });

  // Search results
  const searchQ = useQuery({
    queryKey: ["transactions-search", activeSearch],
    queryFn: () => searchTransactions(activeSearch),
    enabled: !!activeSearch,
  });

  const handleSearch = useCallback(() => {
    if (searchTerm.trim()) {
      setActiveSearch(searchTerm.trim());
      setPage(1);
    } else {
      setActiveSearch("");
    }
  }, [searchTerm]);

  const handleClearSearch = useCallback(() => {
    setSearchTerm("");
    setActiveSearch("");
    setPage(1);
  }, []);

  const transactions: Transaction[] = activeSearch
    ? searchQ.data?.results ?? []
    : txQ.data?.transactions ?? [];

  const totalPages = activeSearch ? 1 : txQ.data?.pages ?? 0;
  const isLoading = activeSearch ? searchQ.isLoading : txQ.isLoading;

  return (
    <Box p={6} maxW="1400px" mx="auto" position="relative">
      <Flex justify="space-between" align="center" mb={6}>
        <Box>
          <Heading size="lg">Transactions</Heading>
          <Text fontSize="sm" color="gray.500">
            {activeSearch
              ? `Search results for "${activeSearch}"`
              : `${txQ.data?.total ?? 0} total transactions`}
          </Text>
        </Box>
        {isLoading && <Spinner size="sm" color="gray.400" />}
      </Flex>

      {/* Search + Filters */}
      <Flex gap={3} mb={4} direction={{ base: "column", md: "row" }}>
        <HStack flex={1}>
          <Input
            placeholder="Search transactions..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            size="sm"
          />
          <Button size="sm" onClick={handleSearch} variant="outline">
            <Search size={14} />
          </Button>
          {activeSearch && (
            <Button size="sm" variant="ghost" onClick={handleClearSearch}>
              Clear
            </Button>
          )}
        </HStack>

        {/* Category filter */}
        <HStack flexWrap="wrap" gap={1}>
          <Badge
            cursor="pointer"
            size="sm"
            variant={!categoryFilter ? "solid" : "outline"}
            onClick={() => {
              setCategoryFilter("");
              setPage(1);
              setActiveSearch("");
            }}
          >
            All
          </Badge>
          {(categoriesQ.data ?? []).slice(0, 8).map((cat) => (
            <Badge
              key={cat}
              cursor="pointer"
              size="sm"
              variant={categoryFilter === cat ? "solid" : "outline"}
              onClick={() => {
                setCategoryFilter(cat);
                setPage(1);
                setActiveSearch("");
              }}
            >
              {cat}
            </Badge>
          ))}
        </HStack>
      </Flex>

      {/* Transaction table */}
      <Box
        bg="white"
        borderRadius="lg"
        borderWidth="1px"
        borderColor="gray.200"
        overflow="hidden"
      >
        {transactions.length === 0 && !isLoading ? (
          <Flex justify="center" py={12}>
            <Text color="gray.400" fontSize="sm">
              No transactions found
            </Text>
          </Flex>
        ) : (
          <Box overflowX="auto">
            <Table.Root size="sm">
              <Table.Header>
                <Table.Row>
                  <Table.ColumnHeader>Date</Table.ColumnHeader>
                  <Table.ColumnHeader>Description</Table.ColumnHeader>
                  <Table.ColumnHeader>Merchant</Table.ColumnHeader>
                  <Table.ColumnHeader>Category</Table.ColumnHeader>
                  <Table.ColumnHeader textAlign="right">Amount</Table.ColumnHeader>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {transactions.map((tx) => {
                  const isIncome = tx.amount > 0;
                  return (
                    <Table.Row
                      key={tx.id}
                      cursor="pointer"
                      _hover={{ bg: "gray.50" }}
                      onClick={() => setSelectedTx(tx)}
                      bg={selectedTx?.id === tx.id ? "blue.50" : undefined}
                    >
                      <Table.Cell fontSize="sm" whiteSpace="nowrap">
                        {tx.date}
                      </Table.Cell>
                      <Table.Cell fontSize="sm" maxW="250px">
                        <Text lineClamp={1}>{tx.description}</Text>
                      </Table.Cell>
                      <Table.Cell fontSize="sm" color="gray.600">
                        {tx.merchant}
                      </Table.Cell>
                      <Table.Cell>
                        <Badge size="sm" variant="subtle">
                          {tx.category}
                        </Badge>
                      </Table.Cell>
                      <Table.Cell
                        textAlign="right"
                        fontWeight="medium"
                        fontSize="sm"
                        color={isIncome ? "green.600" : "red.600"}
                      >
                        {isIncome ? "+" : "-"}{fmt(tx.amount)}
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table.Root>
          </Box>
        )}

        {/* Pagination */}
        {!activeSearch && totalPages > 1 && (
          <Flex justify="center" py={3} borderTop="1px solid" borderColor="gray.100" gap={2}>
            <Button
              size="xs"
              variant="outline"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft size={14} /> Prev
            </Button>
            <Text fontSize="xs" color="gray.500" lineHeight="tall" px={2}>
              Page {page} of {totalPages}
            </Text>
            <Button
              size="xs"
              variant="outline"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages}
            >
              Next <ChevronRight size={14} />
            </Button>
          </Flex>
        )}
      </Box>

      {/* Detail slide-out */}
      {selectedTx && (
        <TransactionDetail
          transaction={selectedTx}
          onClose={() => setSelectedTx(null)}
        />
      )}
    </Box>
  );
}
