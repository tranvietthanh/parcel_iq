import { UserProfile } from "@clerk/nextjs";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Profile — OZ Property Report",
};

export default function ProfilePage() {
  return (
    <div className="flex min-h-screen flex-col items-center bg-zinc-50 px-4 py-12 dark:bg-zinc-950">
      <div className="mb-6 w-full max-w-[55rem]">
        <Link href="/" className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
          ← Back to Map
        </Link>
      </div>
      <UserProfile path="/profile" />
    </div>
  );
}
