// apps/web/app/projects/[id]/page.tsx
import { notFound, redirect } from "next/navigation";
import { auth } from "@/app/api/auth/[...nextauth]/route";

// All UI components from the shared @cursorcode/ui package
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Alert,
  AlertDescription,
  AlertTitle,
  Progress,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  useToast,
} from "@cursorcode/ui";

import { Copy, ExternalLink, Eye, Trash2, AlertCircle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { Suspense } from "react";

// Client component for Copy button
function CopyButton({ text }: { text: string }) {
  "use client";
  const { toast } = useToast();

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(text);
    toast({
      title: "Copied!",
      description: "Project ID copied to clipboard",
    });
  };

  return (
    <Button variant="ghost" size="icon" onClick={copyToClipboard} className="neon-glow">
      <Copy className="h-4 w-4" />
    </Button>
  );
}

interface Project {
  id: string;
  title: string;
  prompt: string;
  status: string;
  error_message?: string;
  logs: string[];
  deploy_url?: string;
  preview_url?: string;
  code_repo_url?: string;
  created_at: string;
  updated_at: string;
  progress?: number;
  current_agent?: string;
  user_id: string;
}

export const dynamic = "force-dynamic";

export default async function ProjectDetailPage({ params }: { params: { id: string } }) {
  const session = await auth();

  if (!session?.user) {
    redirect("/auth/signin");
  }

  const projectId = params.id;

  const res = await fetch(`\( {process.env.NEXT_PUBLIC_API_URL}/projects/ \){projectId}`, {
    headers: {
      Cookie: `access_token=${session.accessToken || ""}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    if (res.status === 404) notFound();
    throw new Error("Failed to fetch project");
  }

  const project: Project = await res.json();

  if (project.user_id !== session.user.id) {
    redirect("/dashboard");
  }

  const totpEnabled = session.user.totp_enabled ?? false;

  return (
    <div className="min-h-screen storyboard-grid bg-background py-10">
      <div className="container mx-auto px-6 max-w-6xl space-y-10">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div>
            <h1 className="text-display text-5xl font-bold tracking-tighter neon-glow">
              {project.title || "Untitled Project"}
            </h1>
            <p className="text-muted-foreground text-xl mt-2">
              Created {formatDistanceToNow(new Date(project.created_at), { addSuffix: true })}
            </p>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <Badge
              variant={
                project.status === "completed" || project.status === "deployed"
                  ? "default"
                  : project.status === "failed"
                  ? "destructive"
                  : project.status === "building"
                  ? "secondary"
                  : "outline"
              }
              className="text-base px-5 py-1.5 neon-glow"
            >
              {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
            </Badge>

            {project.deploy_url && (
              <Button variant="default" className="neon-glow" asChild>
                <a href={project.deploy_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Open Deployed App
                </a>
              </Button>
            )}
          </div>
        </div>

        {/* 2FA Reminder */}
        {!totpEnabled && (
          <Alert className="border-brand-blue/50 bg-card neon-glow">
            <AlertCircle className="h-5 w-5 text-brand-blue" />
            <AlertTitle>Enable 2FA to protect this project</AlertTitle>
            <AlertDescription>
              Your generated code and deployments are valuable.{" "}
              <span className="font-medium">Enable 2FA now.</span>
            </AlertDescription>
          </Alert>
        )}

        {/* Main Grid */}
        <div className="grid gap-8 lg:grid-cols-5">
          {/* Left: Details */}
          <div className="lg:col-span-3 space-y-8">
            <Card className="cyber-card neon-glow border-brand-blue/30">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Project Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-8">
                <div>
                  <h3 className="font-medium mb-3 text-lg">Original Prompt</h3>
                  <div className="bg-muted/50 border border-border p-6 rounded-xl text-sm whitespace-pre-wrap font-light">
                    {project.prompt}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h3 className="font-medium mb-2">Project ID</h3>
                    <div className="flex items-center gap-3 bg-muted/50 border border-border rounded-xl px-4 py-3">
                      <code className="font-mono text-sm flex-1 truncate">{project.id}</code>
                      <CopyButton text={project.id} />
                    </div>
                  </div>

                  {project.code_repo_url && (
                    <div>
                      <h3 className="font-medium mb-2">Code Repository</h3>
                      <Button variant="outline" className="neon-glow w-full" asChild>
                        <a href={project.code_repo_url} target="_blank" rel="noopener noreferrer">
                          View on GitHub →
                        </a>
                      </Button>
                    </div>
                  )}
                </div>

                {/* Delete */}
                <div className="pt-6 border-t border-border">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive" className="neon-glow" size="lg">
                        <Trash2 className="mr-2 h-5 w-5" />
                        Delete Project Permanently
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete this project?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This action is irreversible. All code, deployments, logs and history will be permanently deleted.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={async () => {
                            await fetch(`/api/projects/${project.id}`, { method: "DELETE" });
                            window.location.href = "/dashboard";
                          }}
                          className="bg-destructive hover:bg-destructive/90"
                        >
                          Yes, Delete Forever
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right: Progress & Logs */}
          <div className="lg:col-span-2">
            <Card className="cyber-card neon-glow border-brand-blue/30 h-full">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Generation Progress</CardTitle>
              </CardHeader>
              <CardContent className="space-y-8">
                <div className="space-y-3">
                  <div className="flex justify-between text-sm font-medium">
                    <span>Current Stage</span>
                    <span className="text-brand-glow">{project.current_agent || "Initializing..."}</span>
                  </div>
                  <Progress
                    value={project.progress || 0}
                    className="h-3 bg-muted"
                  />
                </div>

                <div>
                  <h3 className="font-medium mb-3">Live Generation Logs</h3>
                  <div className="bg-black/70 border border-border rounded-2xl p-5 max-h-96 overflow-y-auto font-mono text-xs leading-relaxed text-brand-glow/90">
                    {project.logs?.length ? (
                      project.logs.map((log, i) => (
                        <div key={i} className="py-1.5 border-b border-white/10 last:border-0">
                          {log}
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-12 text-muted-foreground">
                        Waiting for generation to start...
                      </div>
                    )}
                  </div>
                </div>

                {project.error_message && (
                  <Alert variant="destructive" className="neon-glow">
                    <AlertCircle className="h-5 w-5" />
                    <AlertTitle>Build Failed</AlertTitle>
                    <AlertDescription>{project.error_message}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-3 pt-4">
                  {project.preview_url && (
                    <Button variant="outline" className="neon-glow flex-1" asChild>
                      <a href={project.preview_url} target="_blank" rel="noopener noreferrer">
                        <Eye className="mr-2 h-4 w-4" />
                        Live Preview
                      </a>
                    </Button>
                  )}
                  {project.deploy_url && (
                    <Button className="neon-glow flex-1" asChild>
                      <a href={project.deploy_url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="mr-2 h-4 w-4" />
                        Open Deployed App
                      </a>
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
