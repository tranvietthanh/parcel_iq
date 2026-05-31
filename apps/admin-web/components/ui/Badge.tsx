import { getStatusColor } from "@/lib/format";

type BadgeProps = {
  children: string;
  color?: "green" | "yellow" | "red" | "gray";
};

export function Badge({ children, color }: BadgeProps) {
  const colorStyles = {
    green: "bg-green-900 text-green-200",
    yellow: "bg-yellow-900 text-yellow-200",
    red: "bg-red-900 text-red-200",
    gray: "bg-gray-700 text-gray-200",
  };

  const badgeColor = color || getStatusColor(children.toLowerCase());

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorStyles[badgeColor]}`}
    >
      {children}
    </span>
  );
}
