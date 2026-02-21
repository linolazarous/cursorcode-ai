// packages/ui/components/use-toast.tsx
"use client";

import { toast } from "sonner";

// Re-export toast from Sonner with shadcn-style API
export const useToast = () => {
  return {
    toast,
  };
};

// For backward compatibility with code that uses toast() directly
export { toast };
export type { Toast, ExternalToast } from "sonner";
