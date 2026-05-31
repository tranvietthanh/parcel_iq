"use client";

import { useCallback, useEffect, useState } from "react";

type ToastType = "success" | "error" | "info";

type ToastMessage = {
  id: string;
  type: ToastType;
  message: string;
};

const typeStyles: Record<ToastType, string> = {
  success:
    "bg-green-50 border-green-200 text-green-800 dark:bg-green-950 dark:border-green-800 dark:text-green-200",
  error:
    "bg-red-50 border-red-200 text-red-800 dark:bg-red-950 dark:border-red-800 dark:text-red-200",
  info: "bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950 dark:border-blue-800 dark:text-blue-200",
};

const DURATION_MS = 4000;

/** Global toast state — import `showToast` to trigger from anywhere */
let addToast: ((type: ToastType, message: string) => void) | null = null;

export function showToast(type: ToastType, message: string) {
  addToast?.(type, message);
}

/**
 * Toast container — mount once in root layout or map layout.
 */
export default function Toast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const add = useCallback((type: ToastType, message: string) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, DURATION_MS);
  }, []);

  useEffect(() => {
    addToast = add;
    return () => {
      addToast = null;
    };
  }, [add]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-16 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`animate-in slide-in-from-right rounded-lg border px-4 py-3 text-sm shadow-lg ${typeStyles[toast.type]}`}
          role="alert"
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}
