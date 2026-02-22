// apps/web/app/api/auth/[...nextauth]/route.ts
/**
 * NextAuth v5 (Auth.js) Configuration for CursorCode AI
 * Production-ready • Vercel + Render compatible
 */

import NextAuth from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";
import GitHubProvider from "next-auth/providers/github";
import type { JWT } from "next-auth/jwt";
import type { Session, User } from "next-auth";

export const authOptions = {
  providers: [
    CredentialsProvider({
      id: "credentials",
      name: "Email & Password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
        totp_code: { label: "2FA Code (optional)", type: "text" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        try {
          const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
              totp_code: credentials.totp_code || undefined,
            }),
            credentials: "include",
          });

          if (!res.ok) {
            const error = await res.json().catch(() => ({}));
            throw new Error(error.detail || "Invalid credentials");
          }

          const user = await res.json();

          return {
            id: user.id,
            email: user.email,
            name: user.email?.split("@")[0] || "",
            roles: user.roles || ["user"],
            org_id: user.org_id,
            plan: user.plan || "starter",
            credits: user.credits || 0,
          };
        } catch (error) {
          console.error("Credentials auth error:", error);
          return null;
        }
      },
    }),

    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: { prompt: "consent", access_type: "offline", response_type: "code" },
      },
    }),

    GitHubProvider({
      clientId: process.env.GITHUB_ID!,
      clientSecret: process.env.GITHUB_SECRET!,
    }),
  ],

  callbacks: {
    async jwt({ token, user }: { token: JWT; user?: User }) {
      if (user) {
        token.id = user.id;
        token.email = user.email ?? "";           // ← Fixed: safe fallback
        token.roles = user.roles;
        token.org_id = user.org_id;
        token.plan = user.plan;
        token.credits = user.credits;
      }
      return token;
    },

    async session({ session, token }: { session: Session; token: JWT }) {
      if (token && session.user) {
        session.user.id = token.id as string;
        session.user.roles = token.roles as string[];
        session.user.org_id = token.org_id as string;
        session.user.plan = token.plan as string;
        session.user.credits = token.credits as number;
      }
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },

  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60,
  },

  cookies: {
    sessionToken: {
      name: `__Secure-authjs.session-token`,
      options: {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        secure: process.env.NODE_ENV === "production",
      },
    },
  },

  secret: process.env.NEXTAUTH_SECRET,
  trustHost: true,
};

// Export handlers for Vercel / App Router
const { handlers, signIn, signOut, auth } = NextAuth(authOptions);

export { handlers as GET, handlers as POST };
export { auth, signIn, signOut };
