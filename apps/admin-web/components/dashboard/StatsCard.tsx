import { Card, CardContent } from "../ui/Card";
import { formatNumber } from "@/lib/format";

type StatsCardProps = {
  title: string;
  value: number | null;
  subtitle?: string;
};

export function StatsCard({ title, value, subtitle }: StatsCardProps) {
  return (
    <Card>
      <CardContent className="p-6">
        <h3 className="text-sm font-medium text-gray-400">{title}</h3>
        <p className="mt-2 text-3xl font-semibold text-white">
          {formatNumber(value)}
        </p>
        {subtitle && (
          <p className="mt-1 text-sm text-gray-300">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}
