// apps/web/components/theme-provider.tsx
"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Custom ThemeProvider for CursorCode AI
 * Forces dark cyber-futuristic theme to match the logo + advertising video
 */
export function ThemeProvider({ children, ...props }: React.ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="dark"           // Force dark mode (cyber aesthetic)
      enableSystem={false}          // Disable system theme switching
      disableTransitionOnChange     // Instant theme load (no flash)
      storageKey="cursorcode-theme"
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
