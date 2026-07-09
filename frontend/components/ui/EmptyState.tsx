import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

export function EmptyState({ 
  icon: Icon, 
  title, 
  description, 
  action, 
  className 
}: { 
  icon: LucideIcon; 
  title: string; 
  description?: string; 
  action?: React.ReactNode; 
  className?: string 
}) {
  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-16 px-4 gap-4 text-center bg-gray-50 dark:bg-gray-800/50 rounded-2xl border border-dashed border-gray-300 dark:border-gray-700", 
      className
    )}>
      
      {/* Icon Wrapper: Styled with a soft background and border to match the glass cards */}
      <div className="w-16 h-16 rounded-2xl bg-white dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 flex items-center justify-center shadow-sm">
        <Icon size={28} className="text-gray-400 dark:text-gray-500" />
      </div>
      
      {/* Text Container */}
      <div className="max-w-sm mx-auto">
        <p className="text-base font-bold text-gray-900 dark:text-white">{title}</p>
        {description && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      
      {/* Action Button Container */}
      {action && (
        <div className="mt-2">
          {action}
        </div>
      )}
      
    </div>
  );
}