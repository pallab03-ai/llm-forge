import type { Metadata } from "next";
import "./globals.css";
import { AppProviders, themeBootstrapScript } from "@/providers";

export const metadata: Metadata = {
  title: "LLM Forge",
  description: "Production-grade LLMOps platform for fine-tuning, evaluating, and deploying open-source LLMs.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body className="min-h-screen bg-background font-sans antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
