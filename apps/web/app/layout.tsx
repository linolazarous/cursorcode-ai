// apps/web/app/layout.tsx
import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { SessionProvider } from "next-auth/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { auth } from "@/app/api/auth/[...nextauth]/route";

// ────────────────────────────────────────────────
// Global error monitoring
// ────────────────────────────────────────────────
import { reportFrontendError } from "@/lib/monitoring";

if (typeof window !== "undefined") {
  window.onerror = (msg, url, line, col, error) => {
    reportFrontendError(error || new Error(String(msg)), {
      source: "window.onerror",
      url,
      line,
      col,
    });
    return false;
  };

  window.addEventListener("unhandledrejection", (event) => {
    reportFrontendError(event.reason, {
      source: "unhandledrejection",
    });
  });
}

// ────────────────────────────────────────────────
// Fonts — matching logo + video storyboard
// ────────────────────────────────────────────────
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: {
    default: "CursorCode AI",
    template: "%s | CursorCode AI",
  },
  description: "Build Anything. Automatically. With AI.",
  keywords: [
    "AI software engineering",
    "autonomous coding",
    "Grok xAI",
    "CursorCode AI",
    "AI app builder",
  ],
  authors: [{ name: "CursorCode AI Team" }],
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "CursorCode AI",
    description: "Build Anything. Automatically. With AI.",
    images: [{ url: "/og-image.png" }],
  },
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      gcTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${spaceGrotesk.variable} dark`}
    >
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>

      <body className="font-sans antialiased bg-background text-foreground">
        <SessionProvider session={session}>
          <QueryClientProvider client={queryClient}>
            <ThemeProvider
              attribute="class"
              defaultTheme="dark"        // Forced dark mode to match logo + video
              enableSystem={false}       // Disable system theme switching
              disableTransitionOnChange
            >
              {children}

              <Toaster position="top-right" richColors closeButton />
            </ThemeProvider>
          </QueryClientProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
