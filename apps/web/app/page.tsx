// apps/web/app/page.tsx
"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";

// All UI components from the shared @cursorcode/ui package
import { Button, Card, CardContent } from "@cursorcode/ui";

import { ArrowRight, Sparkles, Zap, Rocket, Play, Pause } from "lucide-react";

export default function LandingPage() {
  const [demoPrompt, setDemoPrompt] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [videoPlaying, setVideoPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const examplePrompt = "Build a fitness tracking SaaS with Apple Watch sync, streak counters, and AI workout suggestions";

  // Typing animation for live demo
  useEffect(() => {
    if (isTyping) {
      let i = 0;
      const interval = setInterval(() => {
        setDemoPrompt(examplePrompt.slice(0, i));
        i++;
        if (i > examplePrompt.length) {
          clearInterval(interval);
          setIsTyping(false);
          setTimeout(() => setVideoPlaying(true), 800);
        }
      }, 50);
      return () => clearInterval(interval);
    }
  }, [isTyping]);

  const playDemo = () => {
    setIsTyping(true);
  };

  const toggleVideo = () => {
    if (videoRef.current) {
      if (videoPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setVideoPlaying(!videoPlaying);
    }
  };

  // Get current year for footer
  const currentYear = new Date().getFullYear();

  return (
    <div className="min-h-screen storyboard-grid bg-background text-foreground overflow-hidden">
      {/* Navbar */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="container mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="logo-cursor">
              <span className="text-3xl font-black tracking-tighter text-brand-blue">CC</span>
            </div>
            <span className="text-display text-2xl font-bold tracking-tighter">CursorCode AI</span>
          </div>

          <div className="flex items-center gap-8">
            <Link href="#demo" className="text-sm hover:text-brand-blue transition-colors">Live Demo</Link>
            <Link href="#how" className="text-sm hover:text-brand-blue transition-colors">How it works</Link>
            <Link href="/auth/signin" className="text-sm hover:text-brand-blue transition-colors">Sign in</Link>
            <Button asChild className="neon-glow">
              <Link href="/auth/signup">Start Building Free</Link>
            </Button>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="pt-32 pb-24 relative">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,#1E88E520_0%,transparent_70%)]" />
        <div className="container mx-auto px-6 text-center max-w-5xl relative z-10">
          <div className="inline-flex items-center gap-3 mb-6 px-6 py-2 rounded-full border border-brand-blue/30 bg-card/50 animate-pulse">
            <Sparkles className="h-5 w-5 text-brand-glow" />
            <span className="text-sm font-medium text-brand-glow">Powered by xAI’s Grok • Public Beta</span>
          </div>

          <h1 className="text-display text-7xl md:text-8xl font-bold tracking-tighter leading-none mb-6">
            Build Anything.<br />
            <span className="bg-gradient-to-r from-brand-blue via-brand-glow to-brand-blue bg-clip-text text-transparent">
              Automatically.
            </span>
          </h1>

          <p className="text-2xl text-muted-foreground max-w-2xl mx-auto mb-10">
            The world’s most powerful autonomous AI software engineering platform.<br />
            Natural language → full-stack app in minutes.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Button size="lg" className="neon-glow text-xl h-14 px-10" asChild>
              <Link href="/auth/signup">Start Building Free →</Link>
            </Button>
            <Button size="lg" variant="outline" className="neon-glow text-xl h-14 px-10" onClick={() => document.getElementById("demo")?.scrollIntoView({ behavior: "smooth" })}>
              Watch Live Demo
            </Button>
          </div>
        </div>
      </section>

      {/* LIVE PROMPT DEMO */}
      <section id="demo" className="py-24 border-t border-border bg-black/40">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto text-center mb-12">
            <div className="text-brand-glow text-sm tracking-[4px] mb-3">EXACTLY AS SEEN IN THE VIDEO</div>
            <h2 className="text-display text-5xl font-bold">Watch CursorCode AI Build in Real Time</h2>
          </div>

          <Card className="cyber-card neon-glow overflow-hidden border-brand-blue/40">
            <div className="relative aspect-video bg-black">
              <video
                ref={videoRef}
                src="/videos/demo-video.mp4"
                className="w-full h-full object-cover"
                loop
                muted
                playsInline
                onPlay={() => setVideoPlaying(true)}
                onPause={() => setVideoPlaying(false)}
              />

              {/* Overlay Play Button */}
              {!videoPlaying && (
                <button
                  onClick={toggleVideo}
                  className="absolute inset-0 flex items-center justify-center bg-black/60 hover:bg-black/40 transition-all group"
                >
                  <div className="w-20 h-20 rounded-full border-4 border-white/80 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Play className="h-10 w-10 ml-1 text-white" fill="white" />
                  </div>
                </button>
              )}

              {/* Live Prompt Overlay */}
              <div className="absolute bottom-6 left-6 right-6 bg-black/80 border border-brand-blue/50 rounded-2xl p-6 backdrop-blur">
                <div className="flex items-center gap-3 mb-3">
                  <div className="text-brand-glow text-xs tracking-widest">LIVE DEMO</div>
                  <div className="flex-1 h-px bg-gradient-to-r from-transparent via-brand-blue to-transparent" />
                </div>

                <div className="font-mono text-sm text-brand-glow min-h-[52px]">
                  {isTyping ? demoPrompt : "Type any idea below and watch the magic..."}
                </div>

                <button
                  onClick={playDemo}
                  disabled={isTyping}
                  className="mt-4 w-full h-11 bg-brand-blue hover:bg-brand-blue/90 text-white rounded-xl font-medium flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                >
                  {isTyping ? "Building your app..." : "Try the exact prompt from the video"}
                </button>
              </div>
            </div>
          </Card>

          <p className="text-center text-sm text-muted-foreground mt-6">
            This is the exact 60-second demo from the advertising video • Click to replay
          </p>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="py-24 border-t border-border">
        <div className="container mx-auto px-6 text-center">
          <div className="max-w-2xl mx-auto">
            <h2 className="text-display text-6xl font-bold tracking-tighter mb-6">
              Ready to replace your entire dev team?
            </h2>
            <p className="text-2xl text-muted-foreground mb-10">
              Join thousands of builders using CursorCode AI today.
            </p>
            <Button size="lg" className="neon-glow text-2xl h-16 px-16" asChild>
              <Link href="/auth/signup">Start Free — No Credit Card Required</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-16 bg-card">
        <div className="container mx-auto px-6 text-center text-sm text-muted-foreground">
          © {currentYear} CursorCode AI • Built with Grok by xAI • All rights reserved
        </div>
      </footer>
    </div>
  );
}
