// packages/ui/lib/utils.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * cn - Class Name Utility
 * 
 * Combines `clsx` and `tailwind-merge` for clean, conditional class handling.
 * Used throughout all @cursorcode/ui components for consistent styling.
 * 
 * Supports:
 * - Conditional classes
 * - Tailwind conflicts resolution
 * - Custom brand classes (neon-glow, cyber-card, etc.)
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Optional: Export type for convenience
export type { ClassValue } from "clsx";
