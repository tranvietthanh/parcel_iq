import { Toast, type ToastType } from "./Toast";

export type ToastMessage = {
  id: string;
  message: string;
  type?: ToastType;
  duration?: number;
};

type ToastContainerProps = {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
};

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 pointer-events-none z-50">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            id={toast.id}
            message={toast.message}
            type={toast.type || "info"}
            duration={toast.duration}
            onDismiss={onDismiss}
          />
        </div>
      ))}
    </div>
  );
}
