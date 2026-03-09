import { useToastStore } from "@/store/toast";

const TYPE_STYLES = {
  error: "bg-red-600",
  success: "bg-green-600",
  info: "bg-gray-800",
};

export function ToastContainer() {
  const { toasts, remove } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg text-white text-sm ${TYPE_STYLES[t.type]}`}
        >
          <span className="flex-1 break-words">{t.message}</span>
          <button
            onClick={() => remove(t.id)}
            className="text-white/70 hover:text-white shrink-0 leading-none"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
