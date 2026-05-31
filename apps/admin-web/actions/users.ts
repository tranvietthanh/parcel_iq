"use server";

import { adminAction } from "@/lib/admin-action";
import { revalidatePath } from "next/cache";


export type UserListItem = {
  id: string;
  clerk_user_id: string;
  email: string;
  created_at: string;
  daily_remaining: number;
  purchased_balance: number;
  total_spendable: number;
};

export type UserListResponse = {
  items: UserListItem[];
  pagination: {
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
  };
};

export type LedgerEntry = {
  id: string;
  entry_type: "DAILY_GRANT" | "DOWNLOAD_DEBIT" | "ADMIN_TOPUP";
  delta_credits: number;
  balance_after: number;
  related_property_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type UserDetailResponse = {
  id: string;
  clerk_user_id: string;
  email: string;
  created_at: string;
  wallet: {
    daily_grant: number;
    daily_used: number;
    daily_remaining: number;
    purchased_balance: number;
    total_spendable: number;
    wallet_day_au: string | null;
    wallet_updated_at: string | null;
  };
  recent_ledger: LedgerEntry[];
};

export type TopUpResult = {
  success: boolean;
  credits_added: number;
  new_balance_after: number;
  reason: string;
  actor_admin_id: string;
};

/**
 * Fetch paginated user list with credit summary fields.
 */
export async function listUsers(
  page = 1,
  pageSize = 25,
  search?: string
): Promise<UserListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (search) params.set("search", search);

  return adminAction<UserListResponse>("GET", `/users?${params.toString()}`);
}

/**
 * Fetch a single user's profile, wallet summary, and recent credit ledger.
 */
export async function getUserDetail(userId: string): Promise<UserDetailResponse> {
  return adminAction<UserDetailResponse>("GET", `/users/${userId}`);
}

/**
 * Top up purchased credits for a user.
 * Credits must be a positive integer, reason must be non-empty.
 */
export async function topUpUserCredits(
  userId: string,
  credits: number,
  reason: string
): Promise<TopUpResult> {
  const result = await adminAction<TopUpResult>("POST", `/users/${userId}/credits/top-up`, {
    credits,
    reason,
  });
  revalidatePath(`/users/${userId}`);
  revalidatePath("/users");
  return result;
}

