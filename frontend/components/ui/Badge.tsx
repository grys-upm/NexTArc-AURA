import { cn } from "@/lib/utils";

const variants = {
  default:     "bg-gray-100 text-gray-700 border border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700",
  secondary:   "bg-gray-200 text-gray-600 border border-gray-300 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-600",
  accent:      "bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800/50",
  success:     "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800/50",
  warning:     "bg-yellow-50 text-yellow-800 border border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800/50",
  danger:      "bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-900/30",
  destructive: "bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-900/30",
  info:        "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-900/30 dark:text-sky-400 dark:border-sky-800/50",
  muted:       "bg-transparent text-gray-500 border border-gray-200 dark:text-gray-400 dark:border-gray-800",
  outline:     "bg-transparent text-gray-600 border border-gray-300 dark:text-gray-400 dark:border-gray-700",
};

export function Badge({
  children, variant = "default", className = "", ...props
}: {
  children: React.ReactNode;
  variant?: keyof typeof variants;
  className?: string;
} & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span 
      {...props}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
