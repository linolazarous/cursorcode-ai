// apps/web/components/PromptForm.tsx
"use client";

import { useState, useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/components/ui/use-toast";
import { Loader2, Copy, Send, CheckCircle2 } from "lucide-react";
import { useCopyToClipboard } from "usehooks-ts";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const formSchema = z.object({
  prompt: z.string().min(10, "Prompt must be at least 10 characters").max(2000, "Prompt too long"),
});

type FormData = z.infer<typeof formSchema>;

type AgentStatus = {
  agent: string;
  message: string;
  progress: number;
};

export default function PromptForm() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [statusHistory, setStatusHistory] = useState<AgentStatus[]>([]);
  const [isPolling, setIsPolling] = useState(false);
  const [copiedText, copyToClipboard] = useCopyToClipboard();
  const { toast } = useToast();
  const router = useRouter();
  const logsEndRef = useRef<HTMLDivElement>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
    watch,
  } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { prompt: "" },
    mode: "onChange",
  });

  const promptValue = watch("prompt");

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [statusHistory]);

  // Poll project status
  useEffect(() => {
    if (!projectId || !isPolling) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}`, { credentials: "include" });
        if (!res.ok) throw new Error("Failed to fetch status");

        const data = await res.json();

        setStatusHistory((prev) => {
          const last = prev[prev.length - 1];
          if (last?.agent === data.current_agent) return prev;
          return [
            ...prev,
            {
              agent: data.current_agent || "System",
              message: data.status_message || "Processing...",
              progress: data.progress || 0,
            },
          ];
        });

        if (data.status === "completed" || data.status === "failed") {
          setIsPolling(false);
          toast({
            title: data.status === "completed" ? "Project Ready!" : "Build Failed",
            description: data.status === "completed"
              ? "Your app has been generated and deployed."
              : data.error_message || "Generation failed.",
            variant: data.status === "completed" ? "default" : "destructive",
          });
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [projectId, isPolling, toast]);

  const onSubmit = async (data: FormData) => {
    setIsSubmitting(true);
    setStatusHistory([]);
    setProjectId(null);
    setIsPolling(false);

    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        credentials: "include",
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to start generation");
      }

      const result = await res.json();
      setProjectId(result.project_id);
      setIsPolling(true);

      toast({
        title: "Generation Started",
        description: `Project ID: ${result.project_id}`,
      });

      reset();
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "Generation Failed",
        description: error.message || "Please try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const copyPrompt = () => {
    copyToClipboard(promptValue);
    toast({ title: "Prompt Copied", description: "Ready to reuse" });
  };

  return (
    <div className="space-y-8">
      {/* Prompt Input */}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="relative">
          <Textarea
            placeholder="Describe your dream app in plain English... (e.g. 'Build a fitness tracking SaaS with Apple Watch sync, streak counters, and AI workout suggestions')"
            className="min-h-[160px] resize-y pr-14 bg-card border-border neon-glow focus:border-brand-blue"
            {...register("prompt")}
            disabled={isSubmitting}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-3 bottom-3 neon-glow"
            onClick={copyPrompt}
            disabled={!promptValue.trim()}
          >
            <Copy className="h-4 w-4" />
          </Button>
        </div>

        {errors.prompt && <p className="text-sm text-destructive pl-1">{errors.prompt.message}</p>}

        <Button
          type="submit"
          className="w-full h-14 neon-glow text-lg"
          disabled={isSubmitting || !isValid}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-3 h-5 w-5 animate-spin" />
              Starting Autonomous Generation...
            </>
          ) : (
            <>
              <Send className="mr-3 h-5 w-5" />
              Generate Full App Now
            </>
          )}
        </Button>
      </form>

      {/* Live Generation Panel */}
      {(isSubmitting || projectId) && (
        <Card className="cyber-card neon-glow border-brand-blue/40 overflow-hidden">
          <CardHeader className="border-b border-border pb-4">
            <CardTitle className="text-display text-2xl flex items-center gap-3">
              {isSubmitting ? (
                <Loader2 className="h-6 w-6 animate-spin text-brand-blue" />
              ) : (
                <CheckCircle2 className="h-6 w-6 text-green-400" />
              )}
              Live Generation Status
            </CardTitle>
            {projectId && (
              <div className="text-xs text-muted-foreground font-mono">
                Project ID: <span className="text-brand-glow">{projectId}</span>
              </div>
            )}
          </CardHeader>

          <CardContent className="pt-6 space-y-6">
            {/* Progress Bar */}
            {statusHistory.length > 0 && (
              <div>
                <div className="flex justify-between text-xs mb-2 text-muted-foreground">
                  <span>Progress</span>
                  <span>{statusHistory[statusHistory.length - 1]?.progress || 0}%</span>
                </div>
                <Progress
                  value={statusHistory[statusHistory.length - 1]?.progress || 0}
                  className="h-3 neon-glow"
                />
              </div>
            )}

            {/* Live Logs */}
            <div>
              <div className="text-sm font-medium mb-3 text-brand-glow">AGENT LOGS</div>
              <div className="bg-black/80 border border-brand-blue/30 rounded-2xl p-5 max-h-80 overflow-y-auto font-mono text-xs leading-relaxed text-brand-glow/90">
                {statusHistory.length > 0 ? (
                  statusHistory.map((step, i) => (
                    <div key={i} className="py-2 border-b border-white/10 last:border-0">
                      <span className="text-brand-blue">[{step.agent}]</span> {step.message}
                      {step.progress > 0 && ` — ${step.progress}%`}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-12 text-muted-foreground">Waiting for AI agents to start...</div>
                )}
                <div ref={logsEndRef} />
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              {projectId && (
                <Button variant="default" className="neon-glow flex-1" asChild>
                  <a href={`/projects/${projectId}`}>View Full Project</a>
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => {
                  setIsPolling(false);
                  setStatusHistory([]);
                  setProjectId(null);
                }}
                className="flex-1"
              >
                Clear Logs
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Prompt Examples */}
      <Card className="cyber-card border-dashed border-brand-blue/30">
        <CardHeader>
          <CardTitle className="text-lg">Quick Start Examples</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          {[
            "Build a fitness tracking SaaS with Apple Watch sync, streak counters, and AI workout suggestions",
            "Create a modern task manager with real-time collaboration, dark mode, and Stripe payments",
            "Develop a multi-tenant blog platform with SEO, Markdown editor, and admin dashboard",
          ].map((example, i) => (
            <Button
              key={i}
              variant="outline"
              className="justify-start h-auto py-4 px-5 text-left neon-glow hover:border-brand-blue"
              onClick={() => reset({ prompt: example })}
            >
              {example}
            </Button>
          ))}
        </CardContent>
      </Card>
    </div>
  );
                                    }
