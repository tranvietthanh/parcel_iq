import { notFound } from "next/navigation";
import Link from "next/link";
import { getUserDetail } from "@/actions/users";
import { TopUpForm, LedgerTable } from "./components";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const user = await getUserDetail(id);
    return {
      title: `${user.email} — Users — OZ Property Report Admin`,
    };
  } catch {
    return { title: "User — OZ Property Report Admin" };
  }
}

export default async function UserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let user;
  try {
    user = await getUserDetail(id);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "";
    if (msg.includes("404") || msg.includes("not found")) {
      notFound();
    }
    throw err;
  }


  const { wallet } = user;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Breadcrumb */}
      <div className="mb-6 text-sm text-gray-500">
        <Link href="/users" className="hover:text-gray-300 transition-colors">
          Users
        </Link>
        <span className="mx-2">›</span>
        <span className="text-white">{user.email}</span>
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">{user.email}</h1>
        <p className="text-gray-400 font-mono text-xs mt-1">{user.clerk_user_id}</p>
        <p className="text-gray-500 text-xs mt-1">
          Joined {new Date(user.created_at).toLocaleDateString("en-AU", { dateStyle: "long" })}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Wallet summary cards */}
        <div className="lg:col-span-2 space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">
                Daily Remaining
              </p>
              <p className="text-2xl font-bold text-emerald-400">
                {wallet.daily_remaining}
              </p>
              <p className="text-gray-500 text-xs mt-1">
                of {wallet.daily_grant} granted
              </p>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">
                Purchased
              </p>
              <p className="text-2xl font-bold text-blue-400">
                {wallet.purchased_balance}
              </p>
              <p className="text-gray-500 text-xs mt-1">credits</p>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">
                Total Spendable
              </p>
              <p className="text-2xl font-bold text-white">
                {wallet.total_spendable}
              </p>
              <p className="text-gray-500 text-xs mt-1">
                {wallet.wallet_day_au
                  ? `as of ${wallet.wallet_day_au} AEST`
                  : "credits"}
              </p>
            </div>
          </div>

          {/* Credit activity ledger */}
          <div>
            <h2 className="text-lg font-semibold text-white mb-3">
              Recent Credit Activity
            </h2>
            <LedgerTable entries={user.recent_ledger} />
          </div>
        </div>

        {/* Top-up form */}
        <div className="lg:col-span-1">
          <TopUpForm userId={user.id} currentSpendable={wallet.total_spendable} />
        </div>
      </div>
    </div>
  );
}
