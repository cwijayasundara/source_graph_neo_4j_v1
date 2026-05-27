/**
 * API client for the FinanceGraph backend.
 * Wraps fetch calls to all backend REST endpoints.
 */

import type {
  DashboardSummary,
  TrendPoint,
  CategoryBreakdown,
  TransactionListResponse,
  Transaction,
  Merchant,
  Account,
  TransactionSearchResult,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(15000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export function fetchSummary(period?: string): Promise<DashboardSummary> {
  const params = period ? `?period=${encodeURIComponent(period)}` : "";
  return request<DashboardSummary>(`/dashboard/summary${params}`);
}

export function fetchTrends(
  months = 6,
  category?: string,
): Promise<TrendPoint[]> {
  const params = new URLSearchParams({ months: String(months) });
  if (category) params.set("category", category);
  return request<TrendPoint[]>(`/dashboard/trends?${params}`);
}

export function fetchCategories(
  period?: string,
  accountId?: string,
): Promise<CategoryBreakdown[]> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (accountId) params.set("account_id", accountId);
  return request<CategoryBreakdown[]>(`/dashboard/categories?${params}`);
}

// ─── Transactions ────────────────────────────────────────────────────────────

export function fetchTransactions(opts: {
  page?: number;
  per_page?: number;
  category?: string;
  account_id?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: "date" | "amount";
  sort_order?: "asc" | "desc";
} = {}): Promise<TransactionListResponse> {
  const params = new URLSearchParams();
  if (opts.page) params.set("page", String(opts.page));
  if (opts.per_page) params.set("per_page", String(opts.per_page));
  if (opts.category) params.set("category", opts.category);
  if (opts.account_id) params.set("account_id", opts.account_id);
  if (opts.date_from) params.set("date_from", opts.date_from);
  if (opts.date_to) params.set("date_to", opts.date_to);
  if (opts.sort_by) params.set("sort_by", opts.sort_by);
  if (opts.sort_order) params.set("sort_order", opts.sort_order);
  return request<TransactionListResponse>(`/transactions?${params}`);
}

export function searchTransactions(q: string): Promise<TransactionSearchResult> {
  return request<TransactionSearchResult>(
    `/transactions/search?q=${encodeURIComponent(q)}`,
  );
}

export function fetchTransaction(id: string): Promise<Transaction> {
  return request<Transaction>(`/transactions/${encodeURIComponent(id)}`);
}

// ─── Merchants ───────────────────────────────────────────────────────────────

export function fetchMerchants(
  limit = 100,
): Promise<{ merchants: Merchant[] }> {
  return request<{ merchants: Merchant[] }>(
    `/merchants?limit=${limit}`,
  );
}

export function fetchMerchant(name: string): Promise<Merchant> {
  return request<Merchant>(`/merchants/${encodeURIComponent(name)}`);
}

// ─── Accounts ────────────────────────────────────────────────────────────────

export function fetchAccounts(): Promise<{ accounts: Account[] }> {
  return request<{ accounts: Account[] }>("/accounts");
}

export function fetchBalanceHistory(
  accountId: string,
  months = 12,
): Promise<{ account_id: string; history: { month: string; net: number }[] }> {
  return request(`/accounts/${encodeURIComponent(accountId)}/balance-history?months=${months}`);
}
