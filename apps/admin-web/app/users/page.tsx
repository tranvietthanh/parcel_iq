import { Suspense } from "react";
import Link from "next/link";
import { listUsers } from "@/actions/users";

type SearchParams = {
  page?: string;
  search?: string;
};

export const metadata = {
  title: "Users — OZ Property Report Admin",
  description: "Browse platform users, view credit balances, and manage top-ups.",
};

async function UsersTable({
  page,
  search,
}: {
  page: number;
  search?: string;
}) {
  const data = await listUsers(page, 25, search);

  if (data.items.length === 0) {
    return (
      <div className="text-center py-16 text-gray-500">
        {search ? `No users matching "${search}"` : "No users yet."}
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Clerk ID</th>
              <th className="px-4 py-3 text-right">Daily Remaining</th>
              <th className="px-4 py-3 text-right">Purchased</th>
              <th className="px-4 py-3 text-right">Total Spendable</th>
              <th className="px-4 py-3 text-left">Joined</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {data.items.map((user) => (
              <tr key={user.id} className="hover:bg-gray-900/50 transition-colors">
                <td className="px-4 py-3 font-medium text-white">{user.email}</td>
                <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                  {user.clerk_user_id}
                </td>
                <td className="px-4 py-3 text-right text-emerald-400">
                  {user.daily_remaining}
                </td>
                <td className="px-4 py-3 text-right text-blue-400">
                  {user.purchased_balance}
                </td>
                <td className="px-4 py-3 text-right font-semibold text-white">
                  {user.total_spendable}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {new Date(user.created_at).toLocaleDateString("en-AU")}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/users/${user.id}`}
                    className="text-indigo-400 hover:text-indigo-300 text-xs font-medium transition-colors"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.pagination.total_pages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-400">
          <span>
            Showing {(page - 1) * 25 + 1}–
            {Math.min(page * 25, data.pagination.total_count)} of{" "}
            {data.pagination.total_count} users
          </span>
          <div className="flex gap-2">
            {page > 1 && (
              <Link
                href={`/users?page=${page - 1}${search ? `&search=${search}` : ""}`}
                className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 transition-colors"
              >
                ← Prev
              </Link>
            )}
            {page < data.pagination.total_pages && (
              <Link
                href={`/users?page=${page + 1}${search ? `&search=${search}` : ""}`}
                className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 transition-colors"
              >
                Next →
              </Link>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default async function UsersPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10));
  const search = searchParams.search?.trim() || undefined;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Users</h1>
        <p className="text-gray-400 mt-1">
          Browse platform users, view credit balances, and manage top-ups.
        </p>
      </div>

      {/* Search */}
      <form method="get" className="mb-6">
        <div className="flex gap-3 max-w-md">
          <input
            type="text"
            name="search"
            defaultValue={search}
            placeholder="Search by email or Clerk ID…"
            className="flex-1 px-4 py-2 rounded-lg bg-gray-900 border border-gray-700 text-white placeholder-gray-500 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
          >
            Search
          </button>
          {search && (
            <a
              href="/users"
              className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium transition-colors"
            >
              Clear
            </a>
          )}
        </div>
      </form>

      <Suspense
        fallback={
          <div className="text-center py-16 text-gray-500">Loading users…</div>
        }
      >
        <UsersTable page={page} search={search} />
      </Suspense>
    </div>
  );
}
