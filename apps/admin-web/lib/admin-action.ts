"use server";

import { auth } from "@clerk/nextjs/server";

const ADMIN_BACKEND_URL =
  process.env.ADMIN_BACKEND_URL || "http://localhost:8082";
const ADMIN_SERVICE_TOKEN =
  process.env.ADMIN_SERVICE_TOKEN || "dev-service-token-change-in-prod";

/**
 * Base wrapper for all Server Actions.
 * Verifies Clerk session + org, then calls the Admin Backend API.
 * 
 * This function runs on the server — tokens never reach the browser.
 */
export async function adminAction<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown
): Promise<T> {
  // Step 1: Verify Clerk session and org membership
  const { userId, orgId } = await auth();
  if (!userId || orgId !== process.env.CLERK_ADMIN_ORG_ID) {
    throw new Error("Unauthorised");
  }

  // Step 2: Call Admin Backend API with service token + actor ID
  const url = `${ADMIN_BACKEND_URL}${path}`;
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Service-Token": ADMIN_SERVICE_TOKEN,
      // Forward the admin's Clerk user ID so the backend can record it in audit logs
      "X-Admin-User-Id": userId,
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Get the current admin user's Clerk ID (for activity logging).
 */
export async function getCurrentAdminId(): Promise<string> {
  const { userId } = await auth();
  if (!userId) throw new Error("Unauthorised");
  return userId;
}
