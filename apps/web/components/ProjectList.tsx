// apps/web/components/ProjectList.tsx
"use client";

import { useState } from "react";

// All UI components from the shared @cursorcode/ui package
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@cursorcode/ui";

import { Trash2, ExternalLink, Eye, Sparkles } from "lucide-react";

interface Project {
  id: string;
  title: string;
  status: string;
  deploy_url?: string;
  preview_url?: string;
  created_at: string;
}

interface ProjectListProps {
  initialProjects: Project[];
}

export default function ProjectList({ initialProjects }: ProjectListProps) {
  const [projects, setProjects] = useState(initialProjects);

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/projects/${id}`, { method: "DELETE" });
      if (res.ok) {
        setProjects(projects.filter((p) => p.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {projects.map((project) => (
        <Card
          key={project.id}
          className="cyber-card neon-glow group overflow-hidden border-brand-blue/30 hover:border-brand-blue transition-all duration-300"
        >
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <CardTitle className="text-display text-xl leading-tight truncate group-hover:text-brand-glow transition-colors">
                {project.title || "Untitled Project"}
              </CardTitle>

              <Badge
                variant={
                  project.status === "completed" || project.status === "deployed"
                    ? "default"
                    : project.status === "failed"
                    ? "destructive"
                    : "secondary"
                }
                className="neon-glow text-xs font-medium px-3 py-1"
              >
                {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="pb-4">
            <p className="text-sm text-muted-foreground">
              Created {new Date(project.created_at).toLocaleDateString()}
            </p>
          </CardContent>

          <CardFooter className="flex gap-2 pt-2">
            {project.preview_url && (
              <Button
                variant="outline"
                size="sm"
                className="neon-glow flex-1"
                asChild
              >
                <a href={project.preview_url} target="_blank" rel="noopener noreferrer">
                  <Eye className="mr-2 h-4 w-4" />
                  Preview
                </a>
              </Button>
            )}

            {project.deploy_url && (
              <Button
                variant="default"
                size="sm"
                className="neon-glow flex-1"
                asChild
              >
                <a href={project.deploy_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Open App
                </a>
              </Button>
            )}

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10 neon-glow"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this project?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. All code, deployments, and history will be permanently removed.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => handleDelete(project.id)}
                    className="bg-destructive hover:bg-destructive/90"
                  >
                    Delete Forever
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardFooter>
        </Card>
      ))}

      {projects.length === 0 && (
        <div className="col-span-full py-20 text-center">
          <div className="mx-auto w-16 h-16 rounded-full border border-dashed border-brand-blue/50 flex items-center justify-center mb-6">
            <Sparkles className="h-8 w-8 text-brand-blue/50" />
          </div>
          <h3 className="text-display text-2xl text-muted-foreground">No projects yet</h3>
          <p className="text-muted-foreground mt-2">Your generated apps will appear here</p>
          <Button asChild className="neon-glow mt-6" variant="outline">
            <a href="#create">Create Your First App</a>
          </Button>
        </div>
      )}
    </div>
  );
}
