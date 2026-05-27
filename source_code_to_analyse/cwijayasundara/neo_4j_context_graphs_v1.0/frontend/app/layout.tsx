import type { Metadata } from "next";
import { Provider } from "@/components/Provider";
import { QueryProvider } from "@/components/QueryProvider";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinanceGraph — AI-powered Financial Intelligence",
  description: "Investment management, trading, compliance, and risk assessment",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Provider>
          <QueryProvider>
            <AppShell>{children}</AppShell>
          </QueryProvider>
        </Provider>
      </body>
    </html>
  );
}
