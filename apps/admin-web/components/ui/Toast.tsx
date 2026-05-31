import { useEffect } from "react";

export type ToastType = "success" | "error" | "info" | "warning";

type ToastProps = {
  id: string;
  message: string;
  type?: ToastType;
  duration?: number;
  onDismiss: (id: string) => void;
};

export function Toast({
  id,
  message,
  type = "info",
  duration = 4000,
  onDismiss,
}: ToastProps) {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => onDismiss(id), duration);
      return () => clearTimeout(timer);
    }
  }, [id, duration, onDismiss]);

  const baseStyles =
    "flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium";

  const typeStyles = {
    success: "bg-green-900 border border-green-700 text-green-100",
    error: "bg-red-900 border border-red-700 text-red-100",
    info: "bg-blue-900 border border-blue-700 text-blue-100",
    warning: "bg-yellow-900 border border-yellow-700 text-yellow-100",
  };

  return (
    <div className={`${baseStyles} ${typeStyles[type]} animate-in fade-in slide-in-from-bottom-4 duration-300`}>
      <div className="flex-1">{message}</div>
      <button
        onClick={() => onDismiss(id)}
        className="text-lg leading-none opacity-70 hover:opacity-100 transition"
      >
        ×
      </button>
    </div>
  );
}
