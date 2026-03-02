// apps/web/components/2FASetup.tsx
"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import {
  Button,
  Input,
  Label,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Alert,
  AlertDescription,
  AlertTitle,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  toast,
} from "@cursorcode/ui";

import { Copy, Loader2, CheckCircle2, XCircle, ShieldCheck } from "lucide-react";
import { useCopyToClipboard } from "usehooks-ts";
import { useSession } from "next-auth/react";
import api from "@/lib/api";

const formSchema = z.object({
  code: z.string().length(6, "Must be exactly 6 digits").regex(/^\d{6}$/, "Must be numeric"),
});

type FormData = z.infer<typeof formSchema>;

type TwoFASetupProps = {
  onSuccess?: () => void;
  mode?: "enable" | "disable";
};

export default function TwoFASetup({ onSuccess, mode = "enable" }: TwoFASetupProps) {
  const { data: session, update } = useSession();
  const [copiedText, copyToClipboard] = useCopyToClipboard();

  const [isEnabled, setIsEnabled] = useState(session?.user?.totp_enabled || false);
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [showBackupCodes, setShowBackupCodes] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<FormData>({
    resolver: zodResolver(formSchema),
  });

  // Enable 2FA
  const enable2FA = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await api.post("/auth/2fa/enable");
      const data = res.data;

      setQrCode(data.qr_code_base64);
      setSecret(data.secret);
      setBackupCodes(data.backup_codes);
      setShowBackupCodes(true);

      toast.success("2FA Setup Ready", {
        description: "Scan the QR code with your authenticator app.",
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      toast.error("Setup Failed", { description: err.response?.data?.detail || err.message });
    } finally {
      setIsLoading(false);
    }
  };

  // Verify & Activate
  const onVerify = async (data: FormData) => {
    setIsLoading(true);
    setError(null);

    try {
      await api.post("/auth/2fa/verify", { code: data.code });

      await update({ totp_enabled: true });

      toast.success("2FA Enabled Successfully", {
        description: "Your account is now protected with two-factor authentication.",
      });

      setIsEnabled(true);
      setQrCode(null);
      setSecret(null);
      setBackupCodes([]);
      setShowBackupCodes(false);
      reset();

      onSuccess?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      toast.error("Verification Failed", { description: err.response?.data?.detail || err.message });
    } finally {
      setIsLoading(false);
    }
  };

  // Disable 2FA (note: backend route must exist; placeholder kept)
  const disable2FA = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const code = prompt("Enter your current 2FA code or a backup code:");
      if (!code) return;

      await api.post("/auth/2fa/disable", { code });

      await update({ totp_enabled: false });

      toast.success("2FA Disabled", {
        description: "Two-factor authentication has been turned off.",
      });

      setIsEnabled(false);
      onSuccess?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      toast.error("Disable Failed", { description: err.response?.data?.detail || err.message });
    } finally {
      setIsLoading(false);
    }
  };

  const copySecret = () => {
    if (secret) {
      copyToClipboard(secret);
      toast.success("Secret Copied", { description: "Manual entry key copied" });
    }
  };

  const copyBackupCodes = () => {
    if (backupCodes.length) {
      copyToClipboard(backupCodes.join("\n"));
      toast.success("Backup Codes Copied", { description: "Save these securely!" });
    }
  };

  return (
    <Card className="cyber-card neon-glow border-brand-blue/30 w-full max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="text-display text-2xl flex items-center gap-3">
          <ShieldCheck className="h-7 w-7 text-brand-blue" />
          Two-Factor Authentication
        </CardTitle>
        <CardDescription className="text-base">
          Add an extra layer of security using an authenticator app.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-8">
        {/* Status Bar */}
        <div className="flex items-center justify-between py-3 px-4 bg-card rounded-xl border border-border">
          <div>
            <p className="font-medium">Current Status</p>
            <p className={`text-sm font-semibold ${isEnabled ? "text-green-400" : "text-amber-400"}`}>
              {isEnabled ? "✅ Enabled" : "⚠️ Disabled (recommended to enable)"}
            </p>
          </div>

          {isEnabled ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="neon-glow">
                  Disable 2FA
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Disable 2FA?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will reduce your account security. You will need a 2FA code or backup code to confirm.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={disable2FA} disabled={isLoading}>
                    {isLoading ? "Disabling..." : "Yes, Disable"}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button onClick={enable2FA} disabled={isLoading} className="neon-glow">
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Preparing Setup...
                </>
              ) : (
                "Enable 2FA Now"
              )}
            </Button>
          )}
        </div>

        {/* Error */}
        {error && (
          <Alert variant="destructive" className="neon-glow">
            <XCircle className="h-5 w-5" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Setup Flow */}
        {!isEnabled && qrCode && (
          <div className="space-y-8 pt-4 border-t border-border">
            <div className="grid md:grid-cols-2 gap-8">
              {/* QR Code */}
              <div className="flex flex-col items-center space-y-4">
                <p className="text-center text-sm text-muted-foreground">
                  Scan with Google Authenticator, Authy, or any TOTP app
                </p>
                <div className="bg-white p-4 rounded-2xl shadow-xl border border-brand-blue/20">
                  <img src={qrCode} alt="2FA QR Code" className="w-56 h-56 rounded-xl" />
                </div>
              </div>

              {/* Manual Entry + Backup Codes */}
              <div className="space-y-6">
                <div>
                  <Label>Or enter this secret manually</Label>
                  <div className="flex mt-2">
                    <Input value={secret || ""} readOnly className="font-mono bg-muted neon-glow" />
                    <Button variant="outline" size="icon" onClick={copySecret} className="ml-2 neon-glow">
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <Alert className="neon-glow border-brand-blue/50">
                  <AlertTitle>Save your backup codes!</AlertTitle>
                  <AlertDescription>
                    These one-time codes are your safety net if you lose your phone.
                    {showBackupCodes ? (
                      <div className="mt-4 font-mono text-sm bg-black/70 p-4 rounded-xl border border-border">
                        {backupCodes.map((code, i) => (
                          <div key={i} className="py-1 tracking-widest">
                            {code}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Button variant="secondary" onClick={() => setShowBackupCodes(true)} className="mt-3">
                        Reveal Backup Codes
                      </Button>
                    )}
                    {showBackupCodes && (
                      <Button variant="outline" size="sm" onClick={copyBackupCodes} className="mt-3 neon-glow">
                        Copy All Codes
                      </Button>
                    )}
                  </AlertDescription>
                </Alert>
              </div>
            </div>

            {/* Verification Form */}
            <form onSubmit={handleSubmit(onVerify)} className="space-y-4 border-t pt-6">
              <div>
                <Label htmlFor="code">Enter 6-digit code from your app</Label>
                <Input
                  id="code"
                  placeholder="123456"
                  maxLength={6}
                  {...register("code")}
                  className="mt-2 font-mono text-center text-2xl tracking-[12px] neon-glow"
                />
                {errors.code && <p className="text-sm text-destructive mt-1">{errors.code.message}</p>}
              </div>

              <Button type="submit" className="w-full h-12 neon-glow text-lg" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-3 h-5 w-5 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  "Verify & Activate 2FA"
                )}
              </Button>
            </form>
          </div>
        )}

        {/* 2FA Already Enabled */}
        {isEnabled && !qrCode && (
          <Alert className="neon-glow border-green-500/30 bg-green-950/30">
            <CheckCircle2 className="h-5 w-5 text-green-400" />
            <AlertTitle className="text-green-400">2FA is Active & Protecting Your Account</AlertTitle>
            <AlertDescription className="mt-2">
              Great choice! Your account is now much more secure.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
