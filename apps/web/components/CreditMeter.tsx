// apps/web/components/CreditMeter.tsx
"use client";

import { Progress, Badge, Card, CardContent } from "@cursorcode/ui";
import { Zap } from "lucide-react";

interface CreditMeterProps {
  credits: number;
  plan: string;
}

export function CreditMeter({ credits, plan }: CreditMeterProps) {
  const maxCredits = {
    starter: 10,
    standard: 75,
    pro: 150,
    premier: 600,
    ultra: 2000,
  }[plan] || 10;

  const percentage = Math.min((credits / maxCredits) * 100, 100);
  const isLow = credits < 5;
  const isCritical = credits === 0;

  return (
    <Card className="cyber-card neon-glow border-brand-blue/30 w-72">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-full bg-brand-blue/10">
              <Zap className="h-5 w-5 text-brand-glow" />
            </div>
            <span className="text-display text-sm font-semibold tracking-tight">AI Credits</span>
          </div>

          <Badge
            variant={isCritical ? "destructive" : isLow ? "secondary" : "default"}
            className="neon-glow font-mono text-xs px-3 py-1"
          >
            {credits} / {maxCredits}
          </Badge>
        </div>

        <Progress
          value={percentage}
          className={`h-3 transition-all ${isLow ? "neon-glow" : ""}`}
        />

        {isLow && (
          <p className="text-xs text-destructive mt-3 flex items-center gap-1.5 font-medium">
            ⚠️ Low credits — <span className="underline">Upgrade now</span> to keep building
          </p>
        )}

        <div className="mt-4 text-[10px] text-muted-foreground font-mono text-right tracking-widest">
          {plan.toUpperCase()} PLAN
        </div>
      </CardContent>
    </Card>
  );
}
