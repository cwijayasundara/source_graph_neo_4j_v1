export const KIND_COLORS: Record<string, string> = {
  Module: "#6366f1",
  Package: "#8b5cf6",
  Class: "#f59e0b",
  Enum: "#f59e0b",
  Function: "#10b981",
  Method: "#14b8a6",
  Constant: "#ef4444",
  GlobalVar: "#f97316",
  External: "#6b7280",
  Import: "#94a3b8",
  Decorator: "#ec4899",
  File: "#3b82f6",
  Program: "#0ea5e9",
  Section: "#22d3ee",
  Paragraph: "#2dd4bf",
  Copybook: "#a78bfa",
};

export const REL_COLORS: Record<string, string> = {
  CALLS: "#10b981",
  IMPORTS: "#6366f1",
  INHERITS: "#f59e0b",
  DEFINES: "#94a3b8",
  CONTAINS: "#94a3b8",
  DECORATES: "#ec4899",
  RAISES: "#ef4444",
  CO_CHANGED_WITH: "#8b5cf6",
  AUTHORED_BY: "#3b82f6",
};

export function kindColor(kind: string): string {
  return KIND_COLORS[kind] ?? "#6b7280";
}

export function relColor(type: string): string {
  return REL_COLORS[type] ?? "#475569";
}
