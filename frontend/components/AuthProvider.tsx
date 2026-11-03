"use client";

import { api, postJSON, User, VerificationStatus } from "@/lib/api";
import { LEGAL_VERSION } from "@/lib/legal";
import { SEO_PAGE_SLUGS } from "@/lib/seo-page-slugs";
import { authHref, rememberPostAuthNext } from "@/lib/safe-next";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type AuthActionResult = {
  canProcess: boolean;
  verificationEmailSent?: boolean;
};

type AuthContextValue = {
  user: User | null;
  verification: VerificationStatus | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<AuthActionResult>;
  signup: (name: string, email: string, password: string, acceptLegal: boolean) => Promise<AuthActionResult>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const publicPaths = [
  "/", "/about", "/pricing", "/contact", "/login", "/signup", "/verify-email", "/forgot-password", "/reset-password",
  "/youtube-channel-analyzer",
  "/terms", "/privacy", "/refund-policy", "/acceptable-use", "/copyright", "/legal-notice",
  ...SEO_PAGE_SLUGS.map((slug) => `/${slug}`),
];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [verification, setVerification] = useState<VerificationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const path = usePathname();
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      const nextUser = await api<User>("/auth/me");
      setUser(nextUser);
      try {
        setVerification(await api<VerificationStatus>("/auth/verification-status"));
      } catch {
        // Backend enforcement remains authoritative. Keep the signed-in user,
        // but do not assume AI processing is unlocked when verification state
        // could not be confirmed.
        setVerification(null);
      }
    } catch {
      setUser(null);
      setVerification(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (loading) return;
    const isPublic = publicPaths.includes(path);
    if (!user && !isPublic) {
      rememberPostAuthNext(path);
      router.replace(authHref("/login", path));
      return;
    }
    if (user && !isPublic && verification?.required && !verification.can_process) {
      rememberPostAuthNext(path);
      router.replace(authHref("/verify-email", path));
    }
  }, [loading, user, verification, path, router]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    verification,
    loading,
    refresh,
    login: async (email, password) => {
      const response = await postJSON<{ user: User }>("/auth/login", { email, password });
      setUser(response.user);
      try {
        const status = await api<VerificationStatus>("/auth/verification-status");
        setVerification(status);
        return { canProcess: status.can_process };
      } catch {
        // Authentication succeeded, but verification state is unknown. Route
        // through the verification screen rather than failing open to creator
        // compute; the backend remains the final authority either way.
        setVerification(null);
        return { canProcess: false };
      }
    },
    signup: async (name, email, password, acceptLegal) => {
      const response = await postJSON<{
        user: User;
        verification_email_sent: boolean;
        verification: VerificationStatus;
      }>("/auth/signup", {
        name,
        email,
        password,
        accept_legal: acceptLegal,
        legal_version: LEGAL_VERSION,
      });
      setUser(response.user);
      setVerification(response.verification);
      return {
        canProcess: response.verification.can_process,
        verificationEmailSent: response.verification_email_sent,
      };
    },
    logout: async () => {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
      setVerification(null);
      router.push("/");
    },
  }), [user, verification, loading, refresh, router]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be inside AuthProvider");
  return value;
}
