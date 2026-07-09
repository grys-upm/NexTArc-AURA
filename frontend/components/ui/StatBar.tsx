import { cn } from "@/lib/utils";

export function StatBar({ 
  value, 
  max = 100, 
  color = "blue-500", 
  label, 
  unit = "%" 
}: { 
  value: number; 
  max?: number; 
  color?: string; 
  label?: string; 
  unit?: string 
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100)); // Added Math.max to prevent negative widths
  
  // Explicitly map the string values to Tailwind classes so the compiler doesn't purge them
  const colorMap: Record<string, string> = {
    "blue-500": "bg-blue-500",
    "emerald-500": "bg-emerald-500",
    "red-500": "bg-red-500",
    "orange-500": "bg-orange-500",
    "yellow-500": "bg-yellow-500",
    "pink-500": "bg-pink-500",
  };
  
  // Default to blue if an unrecognized color is passed
  const barClass = colorMap[color] || "bg-blue-500"; 

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <div className="flex justify-between items-center">
          <span className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            {label}
          </span>
          <span className="text-xs font-mono font-medium text-gray-900 dark:text-white">
            {value.toFixed(1)}{unit}
          </span>
        </div>
      )}
      
      {/* Track Background */}
      <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden border border-gray-200 dark:border-gray-700/50">
        {/* Progress Fill */}
        <div 
          className={cn("h-full rounded-full transition-all duration-500 shadow-sm", barClass)} 
          style={{ width: `${pct}%` }} 
        />
      </div>
    </div>
  );
}