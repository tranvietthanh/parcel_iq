"use client";

import {
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from "@clerk/nextjs";
import Link from "next/link";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { useApiClient } from "@/lib/api";

type AuthGuardProps = {
  children: ReactNode;
  fallback?: ReactNode;
};

/**
 * Wraps content that requires authentication.
 * Shows sign-in prompt when user is not authenticated.
 */
export default function AuthGuard({ children, fallback }: AuthGuardProps) {
  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        {fallback ?? (
          <div className="flex flex-col items-center justify-center gap-4 py-12">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Sign in to access this content
            </p>
            <SignInButton mode="modal">
              <button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                Sign In
              </button>
            </SignInButton>
          </div>
        )}
      </SignedOut>
    </>
  );
}

type WalletSummary = {
  daily_remaining: number;
  purchased_balance: number;
  total_spendable: number;
};

function NavLinks() {
  const { isSignedIn } = useAuth();
  const api = useApiClient();
  const [credits, setCredits] = useState<number | null>(null);

  const fetchCredits = useCallback(async () => {
    if (!isSignedIn) return;
    try {
      const w = await api.get<WalletSummary>("/api/credits/me");
      setCredits(w.total_spendable);
    } catch {
      // non-fatal — badge just won't show a number
    }
  }, [isSignedIn, api]);

  useEffect(() => {
    fetchCredits();
  }, [fetchCredits]);

  return (
    <div className="flex items-center gap-1">
      <Link
        href="/my-properties"
        className="flex items-center gap-1 whitespace-nowrap rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
      >
        My Properties
      </Link>
      <Link
        href="/pricing"
        className="flex items-center gap-1.5 whitespace-nowrap rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 shadow-sm transition hover:bg-indigo-100 dark:border-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 dark:hover:bg-indigo-900"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 16 16"
          fill="currentColor"
          className="h-3.5 w-3.5"
        >
          <path d="M8.75 11.25a.75.75 0 0 0-1.5 0v.5h-.5a.75.75 0 0 0 0 1.5h.5v.5a.75.75 0 0 0 1.5 0v-.5h.5a.75.75 0 0 0 0-1.5h-.5v-.5Z" />
          <path
            fillRule="evenodd"
            d="M1 4.75C1 3.784 1.784 3 2.75 3h10.5c.966 0 1.75.784 1.75 1.75v6.5A1.75 1.75 0 0 1 13.25 13H2.75A1.75 1.75 0 0 1 1 11.25v-6.5Zm1.75-.25a.25.25 0 0 0-.25.25v6.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-6.5a.25.25 0 0 0-.25-.25H2.75Z"
            clipRule="evenodd"
          />
        </svg>
        {credits !== null ? (
          <span>
            {credits} credit{credits !== 1 ? "s" : ""}
          </span>
        ) : (
          <span>Credits</span>
        )}
      </Link>
    </div>
  );
}

/**
 * Auth controls + navigation for the map toolbar.
 * Signed in → nav links + credit balance + Clerk UserButton.
 * Signed out → Sign In button.
 */
export function UserAvatar() {
  return (
    <div className="flex items-center gap-2">
      <SignedIn>
        <NavLinks />
        <UserButton
          userProfileUrl="/profile"
          userProfileMode="navigation"
          afterSignOutUrl="/"
        />
      </SignedIn>
      <SignedOut>
        <SignInButton mode="modal">
          <button className="flex items-center gap-1.5 whitespace-nowrap rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 16 16"
              fill="currentColor"
              className="h-3.5 w-3.5"
            >
              <path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM12.735 14c.618 0 1.093-.561.872-1.139a6.002 6.002 0 0 0-11.215 0c-.22.578.254 1.139.872 1.139h9.47Z" />
            </svg>
            Sign in
          </button>
        </SignInButton>
      </SignedOut>
    </div>
  );
}
