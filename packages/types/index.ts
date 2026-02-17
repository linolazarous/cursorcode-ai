// packages/types/index.ts
// Shared TypeScript definitions for CursorCode AI
// Used across frontend, backend, and shared packages

// ====================== USER ======================
export interface User {
  id: string;
  email: string;
  name?: string | null;
  image?: string | null;
  
  roles: string[];
  plan: Plan;
  credits: number;
  
  totp_enabled: boolean;
  
  createdAt: Date;
  updatedAt: Date;
  
  // Relations (optional when populated)
  projects?: Project[];
}

// ====================== PROJECT ======================
export interface Project {
  id: string;
  title: string;
  prompt: string;
  
  status: ProjectStatus;
  progress: number;
  current_agent?: string | null;
  
  logs: string[];
  error_message?: string | null;
  
  deploy_url?: string | null;
  preview_url?: string | null;
  code_repo_url?: string | null;
  
  userId: string;
  user?: User;
  
  createdAt: Date;
  updatedAt: Date;
}

// ====================== ENUMS & CONSTANTS ======================
export type Plan = "starter" | "standard" | "pro" | "premier" | "ultra";

export type ProjectStatus = 
  | "queued"
  | "building"
  | "completed"
  | "failed"
  | "deployed";

// ====================== NEXTAUTH TYPES ======================
export interface Account {
  id: string;
  userId: string;
  provider: string;
  providerAccountId: string;
  refresh_token?: string | null;
  access_token?: string | null;
  expires_at?: number | null;
}

export interface Session {
  id: string;
  sessionToken: string;
  userId: string;
  expires: Date;
}

// ====================== UTILITY TYPES ======================
export type UserWithProjects = User & { projects: Project[] };

export type ProjectWithUser = Project & { user: User };

// ====================== API RESPONSE TYPES ======================
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  hasMore: boolean;
}
