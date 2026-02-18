// apps/web/app/dashboard/page.tsx
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
import { CreditMeter } from "@/components/CreditMeter";
import PromptForm from "@/components/PromptForm";
import ProjectList from "@/components/ProjectList";
import TwoFASetup from "@/components/2FASetup";

// Update these imports to use the UI package
import { Button, Card, Alert } from "@cursorcode/ui";
import { CardContent, CardHeader, CardTitle, CardDescription } from "@cursorcode/ui";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@cursorcode/ui";

// AlertDialog components might not be in your UI package yet
// If they are, import them from @cursorcode/ui, otherwise keep as is
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

import { ShieldCheck, AlertCircle, CheckCircle2 } from "lucide-react";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
    redirect("/auth/signin");
  }

  const user = session.user;
  const credits = user.credits ?? 10;
  const plan = user.plan ?? "starter";
  const totpEnabled = user.totp_enabled ?? false;

  const projectsRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
    headers: {
      Cookie: `access_token=${session.accessToken || ""}`,
    },
    cache: "no-store",
  });

  const initialProjects = projectsRes.ok ? await projectsRes.json() : [];

  return (
    <div className="min-h-screen storyboard-grid bg-background py-8">
      <div className="container mx-auto space-y-10 px-6 max-w-7xl">
        {/* Branded Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div>
            <h1 className="text-display text-5xl font-bold tracking-tighter text-foreground neon-glow">
              CursorCode AI
            </h1>
            <p className="text-2xl text-muted-foreground mt-1">Build Anything. Automatically. With AI.</p>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <CreditMeter credits={credits} plan={plan} />
            <Button variant="outline" className="neon-glow" asChild>
              <a href="/billing">Upgrade Plan</a>
            </Button>
          </div>
        </div>

        {/* 2FA Status Card */}
        <Card className="cyber-card neon-glow border-brand-blue">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-3 text-display text-2xl">
              <ShieldCheck className="h-6 w-6 text-brand-glow" />
              Two-Factor Authentication
            </CardTitle>
          </CardHeader>
          <CardContent>
            {totpEnabled ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-green-400">
                  <CheckCircle2 className="h-6 w-6" />
                  <span className="text-lg font-medium">2FA is enabled — your account is protected</span>
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm" className="neon-glow">
                      Disable 2FA
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Disable Two-Factor Authentication?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will lower your account security. You will need a current 2FA code or backup code to confirm.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction asChild>
                        <TwoFASetup mode="disable" onSuccess={() => window.location.reload()} />
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ) : (
              <div className="space-y-6">
                <Alert className="border-brand-blue/50 bg-card">
                  <AlertCircle className="h-5 w-5 text-brand-blue" />
                  <AlertTitle>Enable 2FA for maximum security</AlertTitle>
                  <AlertDescription>
                    Protect your projects and generated code with an extra layer of authentication.
                  </AlertDescription>
                </Alert>
                <TwoFASetup onSuccess={() => window.location.reload()} />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Main Tabs */}
        <Tabs defaultValue="create" className="space-y-8">
          <TabsList className="grid w-full grid-cols-2 bg-card border border-border neon-glow">
            <TabsTrigger value="create" className="text-lg py-3 data-[state=active]:text-brand-blue">
              Create New Project
            </TabsTrigger>
            <TabsTrigger value="projects" className="text-lg py-3 data-[state=active]:text-brand-blue">
              Your Projects
            </TabsTrigger>
          </TabsList>

          {/* Create Tab */}
          <TabsContent value="create">
            <Card className="cyber-card neon-glow">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Build Something New</CardTitle>
                <CardDescription className="text-lg">
                  Describe your app in plain English — CursorCode AI will design, code, test, secure, deploy, and maintain it automatically.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-2">
                <PromptForm />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Projects Tab */}
          <TabsContent value="projects">
            <Suspense fallback={
              <div className="text-center py-20 text-muted-foreground">Loading your projects...</div>
            }>
              <ProjectList initialProjects={initialProjects} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
