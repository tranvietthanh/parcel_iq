import { getStats } from "@/actions/stats";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { StatsCard } from "@/components/dashboard/StatsCard";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const stats = await getStats();
  const quotaPercentage = Math.round((stats.gemini_quota.used_today / stats.gemini_quota.daily_limit) * 100);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-white">Dashboard</h2>
        <p className="mt-2 text-base text-gray-300">
          System overview and key metrics
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Properties"
          value={stats.total_properties}
        />
        <StatsCard
          title="Reports Ready"
          value={stats.reports_ready}
        />
        <StatsCard
          title="Awaiting Review"
          value={stats.awaiting_review}
          subtitle={
            stats.awaiting_review > 0 ? "Action required" : "All clear"
          }
        />
        <StatsCard
          title="Failed (7d)"
          value={stats.failed_7d}
          subtitle={
            stats.failed_7d > 0 ? "Check logs" : "No failures"
          }
        />
        <StatsCard
          title="LGA Coverage"
          value={stats.lga_coverage}
          subtitle="LGAs with reports"
        />
        <StatsCard
          title="Sales (MTD)"
          value={stats.sales_mtd}
        />
        <StatsCard
          title="Revenue (MTD)"
          value={stats.revenue_mtd}
          subtitle="AUD"
        />
        <Card className="bg-gray-900 border-gray-800">
          <CardHeader>
            <h3 className="text-sm font-medium text-gray-400">Gemini API Quota</h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-semibold text-white">
                  {stats.gemini_quota.used_today}/{stats.gemini_quota.daily_limit}
                </span>
                <span className={`text-sm font-medium ${
                  quotaPercentage >= 90 ? 'text-red-400' :
                  quotaPercentage >= 70 ? 'text-yellow-400' :
                  'text-green-400'
                }`}>
                  {quotaPercentage}%
                </span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div 
                  className={`h-2 rounded-full ${
                    quotaPercentage >= 90 ? 'bg-red-500' :
                    quotaPercentage >= 70 ? 'bg-yellow-500' :
                    'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(quotaPercentage, 100)}%` }}
                />
              </div>
              <p className="text-xs text-gray-500">
                {stats.gemini_quota.remaining} requests remaining
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <h3 className="text-xl font-semibold text-white">Quick Actions</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <a
              href="/scrape"
              className="block p-4 border border-gray-700 rounded-lg hover:bg-gray-800 transition"
            >
              <h4 className="font-medium text-white">Trigger Scrape</h4>
              <p className="mt-1 text-sm text-gray-400">
                Start a new scraping job for selected LGAs
              </p>
            </a>
            <a
              href="/properties"
              className="block p-4 border border-gray-700 rounded-lg hover:bg-gray-800 transition"
            >
              <h4 className="font-medium text-white">Review Properties</h4>
              <p className="mt-1 text-sm text-gray-400">
                Open property details and approve/reject flagged reports
              </p>
            </a>
            <a
              href="/sources"
              className="block p-4 border border-gray-700 rounded-lg hover:bg-gray-800 transition"
            >
              <h4 className="font-medium text-white">Manage Sources</h4>
              <p className="mt-1 text-sm text-gray-400">
                Configure data source adapters
              </p>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
