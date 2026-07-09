import { cn } from "@/lib/utils";

const statusStyles: Record<string, string> = {
  // Emerald for healthy/ready/running states
  online: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
  ready: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
  running: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
  
  // Yellow/Pulse for in-progress states
  compiling: "bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.6)] animate-pulse",
  
  // Sky Blue for sent/transmitting
  sent: "bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.6)]",
  
  // Red for errors and stopped states
  failed: "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]",
  stopped: "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]",
  
  // Flat grays for inactive states (no glow)
  offline: "bg-gray-400 dark:bg-gray-600",
  pending: "bg-gray-400 dark:bg-gray-600",
  muted: "bg-gray-400 dark:bg-gray-600",
};

export function StatusDot({ 
  status, 
  className 
}: { 
  status: string; 
  className?: string 
}) {
  // Normalize the status string and fallback to a muted gray if it's unrecognized
  const styleClass = statusStyles[status?.toLowerCase()] || statusStyles.muted;

  return (
    <span 
      className={cn(
        "inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 transition-colors duration-300", 
        styleClass, 
        className
      )} 
      aria-label={`Status: ${status}`}
    />
  );
}