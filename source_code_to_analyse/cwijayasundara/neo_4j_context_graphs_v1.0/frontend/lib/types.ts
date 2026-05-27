/** Shared TypeScript types for the FinanceGraph frontend. */

export interface Transaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  balance: number;
  payment_method: string | null;
  merchant: string;
  category: string;
  account_id: string;
  person?: string | null;
}

export interface TransactionListResponse {
  transactions: Transaction[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface DashboardSummary {
  total_in: number;
  total_out: number;
  net: number;
  transaction_count: number;
  top_category: { category: string; total: number } | null;
  top_merchant: { merchant: string; total: number } | null;
}

export interface TrendPoint {
  month: string;
  total_in: number;
  total_out: number;
  net: number;
}

export interface CategoryBreakdown {
  category: string;
  total: number;
  percentage: number;
  transaction_count: number;
  top_merchant: string | null;
}

export interface Merchant {
  merchant: string;
  category: string;
  transaction_count: number;
  total_spent: number;
  avg_transaction?: number;
  active_months?: string[];
}

export interface Account {
  account_id: string;
  account_type: string;
  institution: string;
  holder: string;
  latest_balance: number;
  txn_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  chart_spec?: ChartSpec;
}

export interface ChartSpec {
  chart_type: "bar" | "line" | "pie";
  title: string;
  data: Record<string, unknown>[];
  x_key: string;
  y_key: string;
}

export interface GraphNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

export interface GraphRelationship {
  id: string;
  type: string;
  source: string;
  target: string;
}

export interface TransactionSearchResult {
  results: Transaction[];
}
