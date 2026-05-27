/**
 * Domain configuration for FinanceGraph
 * Personal finance transaction analysis
 */

export const DOMAIN = {
  id: "personal-finance",
  name: "FinanceGraph",
  description: "Personal finance assistant — spending analysis, savings advice, and transaction insights",
  tagline: "AI-powered Personal Finance",
};

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const NODE_COLORS: Record<string, string> = {
  Account: "#0ea5e9",
  Transaction: "#f59e0b",
  Merchant: "#3b82f6",
  Category: "#22c55e",
  Person: "#8b5cf6",
  Institution: "#06b6d4",
  TimePeriod: "#94a3b8",
  Statement: "#f97316",
  DecisionTrace: "#dc2626",
  Event: "#f97316",
  Location: "#a855f7",
  Object: "#eab308",
  Organization: "#3b82f6",
};

export const NODE_SIZES: Record<string, number> = {
  Person: 32,
  Account: 30,
  Institution: 24,
  Statement: 20,
  Transaction: 10,
  Merchant: 24,
  Category: 22,
  TimePeriod: 16,
};

export const DEFAULT_CYPHER = `MATCH (p:Person)-[r]-(n) RETURN p, r, n LIMIT 100`;

export const SCHEMA_NODE_SIZE = 30;
export const SCHEMA_REL_COLOR = "#94a3b8";

export type GraphPresetId =
  | "overview"
  | "accounts"
  | "spending"
  | "merchants"
  | "categories"
  | "statements"
  | "explore-all";

export interface GraphPreset {
  id: GraphPresetId;
  label: string;
}

export const GRAPH_PRESETS: GraphPreset[] = [
  { id: "overview", label: "Overview" },
  { id: "accounts", label: "Accounts" },
  { id: "spending", label: "Spending" },
  { id: "merchants", label: "Merchants" },
  { id: "categories", label: "Categories" },
  { id: "statements", label: "Statements" },
  { id: "explore-all", label: "Explore All" },
];

export interface GraphData {
  results?: Record<string, unknown>[];
  nodes?: Record<string, unknown>[];
  relationships?: Record<string, unknown>[];
  preset?: GraphPresetId;
  stats?: Record<string, number>;
}

export interface DemoScenario {
  name: string;
  prompts: string[];
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    name: "Spending Analysis",
    prompts: [
      "What was my biggest expense in January 2026?",
      "How much did I spend on groceries last month?",
      "Show me all my Tesco transactions in 2025",
    ],
  },
  {
    name: "Savings & Advice",
    prompts: [
      "How can I save money on my grocery spending?",
      "Am I spending too much on subscriptions?",
      "What are my top 5 recurring payments?",
    ],
  },
  {
    name: "Trends & Comparisons",
    prompts: [
      "Compare my spending in January vs February 2026",
      "How much was my salary in March 2025?",
      "What is my average monthly spend on dining out?",
    ],
  },
];
