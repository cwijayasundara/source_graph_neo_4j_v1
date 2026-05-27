"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  Box,
  Flex,
  Heading,
  Text,
  HStack,
  Button,
} from "@chakra-ui/react";
import {
  LayoutDashboard,
  ArrowLeftRight,
  Network,
  MessageSquare,
} from "lucide-react";
import { ChatSidebar } from "./ChatSidebar";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Transactions", href: "/transactions", icon: ArrowLeftRight },
  { label: "Graph", href: "/graph", icon: Network },
  { label: "AI Insights", href: "/insights", icon: MessageSquare },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Flex direction="column" h="100dvh">
      {/* Top navigation bar */}
      <Flex
        bg="gray.900"
        color="white"
        px={6}
        py={3}
        justify="space-between"
        align="center"
        flexShrink={0}
      >
        <HStack gap={6}>
          <Box>
            <Heading size="md">FinanceGraph</Heading>
            <Text fontSize="xs" color="gray.400">
              AI-powered Financial Intelligence
            </Text>
          </Box>

          {/* Tab navigation */}
          <HStack gap={1} display={{ base: "none", md: "flex" }}>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive =
                pathname === item.href ||
                (item.href === "/graph" && pathname === "/") ||
                (item.href === "/insights" && pathname === "/insights");
              return (
                <Link key={item.href} href={item.href}>
                  <Button
                    size="sm"
                    variant={isActive ? "solid" : "ghost"}
                    colorPalette={isActive ? "blue" : undefined}
                    color={isActive ? "white" : "gray.300"}
                    _hover={{ color: "white", bg: isActive ? undefined : "gray.700" }}
                  >
                    <Icon size={14} />
                    {item.label}
                  </Button>
                </Link>
              );
            })}
          </HStack>
        </HStack>
      </Flex>

      {/* Mobile tab bar */}
      <HStack
        display={{ base: "flex", md: "none" }}
        justify="space-around"
        py={1}
        bg="gray.800"
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}>
              <Flex
                direction="column"
                align="center"
                px={2}
                py={1}
                color={isActive ? "blue.300" : "gray.400"}
              >
                <Icon size={16} />
                <Text fontSize="2xs">{item.label}</Text>
              </Flex>
            </Link>
          );
        })}
      </HStack>

      {/* Main content area with optional chat sidebar */}
      <Flex flex={1} overflow="hidden">
        <ChatSidebar />
        <Box flex={1} overflow="auto" bg="gray.50">
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}
