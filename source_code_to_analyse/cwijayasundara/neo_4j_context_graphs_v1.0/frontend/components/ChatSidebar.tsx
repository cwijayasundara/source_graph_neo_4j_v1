"use client";

import { useState, useRef, useEffect } from "react";
import {
  Box,
  Flex,
  Text,
  Textarea,
  IconButton,
  VStack,
  Heading,
  Button,
  HStack,
  Spinner,
} from "@chakra-ui/react";
import {
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  RotateCcw,
  Bot,
  User,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat } from "@/lib/sse";
import { ChartRenderer } from "./ChartRenderer";

export function ChatSidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const { messages, isStreaming, sendMessage, clearMessages } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    if (!input.trim() || isStreaming) return;
    sendMessage(input);
    setInput("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // Collapsed toggle button
  if (!isOpen) {
    return (
      <Box
        position="fixed"
        left={0}
        top="50%"
        transform="translateY(-50%)"
        zIndex={20}
      >
        <IconButton
          aria-label="Open AI Chat"
          onClick={() => setIsOpen(true)}
          size="md"
          colorPalette="blue"
          borderLeftRadius={0}
          borderRightRadius="md"
          boxShadow="md"
        >
          <PanelLeftOpen size={18} />
        </IconButton>
      </Box>
    );
  }

  return (
    <Flex
      direction="column"
      w={{ base: "100%", md: "340px" }}
      h="100%"
      bg="white"
      borderRight="1px solid"
      borderColor="gray.200"
      flexShrink={0}
      position="relative"
    >
      {/* Header */}
      <Flex
        px={3}
        py={2}
        borderBottom="1px solid"
        borderColor="gray.200"
        justify="space-between"
        align="center"
      >
        <HStack gap={2}>
          <MessageSquare size={16} />
          <Heading size="sm">AI Insights</Heading>
        </HStack>
        <HStack gap={1}>
          {messages.length > 0 && (
            <Button size="xs" variant="ghost" onClick={clearMessages}>
              <RotateCcw size={12} />
            </Button>
          )}
          <IconButton
            aria-label="Close chat"
            size="xs"
            variant="ghost"
            onClick={() => setIsOpen(false)}
          >
            <PanelLeftClose size={16} />
          </IconButton>
        </HStack>
      </Flex>

      {/* Messages */}
      <VStack
        flex={1}
        overflow="auto"
        px={3}
        py={2}
        gap={3}
        align="stretch"
      >
        {messages.length === 0 && !isStreaming && (
          <Flex direction="column" align="center" justify="center" flex={1} py={8}>
            <Bot size={28} color="#A0AEC0" />
            <Text fontSize="sm" color="gray.400" mt={2} textAlign="center">
              Ask about your financial data
            </Text>
          </Flex>
        )}

        {messages.map((msg, i) => (
          <Flex key={i} gap={2} alignItems="flex-start">
            <Flex
              w={6}
              h={6}
              borderRadius="full"
              bg={msg.role === "user" ? "blue.500" : "gray.600"}
              color="white"
              align="center"
              justify="center"
              flexShrink={0}
              mt={0.5}
            >
              {msg.role === "user" ? (
                <User size={12} />
              ) : (
                <Bot size={12} />
              )}
            </Flex>
            <Box
              bg={msg.role === "user" ? "blue.50" : "gray.50"}
              px={3}
              py={2}
              borderRadius="lg"
              flex={1}
              fontSize="sm"
            >
              {msg.role === "assistant" ? (
                <>
                  <Box className="markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </Box>
                  {msg.chart_spec && (
                    <ChartRenderer spec={msg.chart_spec} />
                  )}
                </>
              ) : (
                <Text whiteSpace="pre-wrap">{msg.content}</Text>
              )}
            </Box>
          </Flex>
        ))}

        {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
          <HStack gap={2} px={2}>
            <Spinner size="xs" />
            <Text fontSize="xs" color="gray.500">
              Thinking...
            </Text>
          </HStack>
        )}

        <div ref={messagesEndRef} />
      </VStack>

      {/* Input */}
      <Box px={3} py={2} borderTop="1px solid" borderColor="gray.200">
        <Box
          borderWidth="1px"
          borderColor="gray.200"
          rounded="lg"
          _focusWithin={{
            borderColor: "blue.400",
            boxShadow: "0 0 0 1px var(--chakra-colors-blue-400)",
          }}
          transition="border-color 0.2s, box-shadow 0.2s"
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about finances..."
            border="none"
            _focus={{ boxShadow: "none" }}
            resize="none"
            rows={2}
            fontSize="sm"
            px={3}
            py={2}
          />
          <Flex px={2} py={1} justify="flex-end">
            <IconButton
              aria-label="Send"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              size="xs"
              colorPalette="blue"
              rounded="md"
            >
              <Send size={12} />
            </IconButton>
          </Flex>
        </Box>
      </Box>
    </Flex>
  );
}
