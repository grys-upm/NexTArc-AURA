import { cn } from "@/lib/utils";

export function Card({ 
  children, 
  className = "", 
  glow 
}: { 
  children: React.ReactNode; 
  className?: string; 
  glow?: boolean 
}) {
  return (
    <div className={cn(
      "bg-white/60 dark:bg-gray-900/40 backdrop-blur-xl border border-slate-200/60 dark:border-gray-800 rounded-2xl p-5 shadow-sm transition-all duration-300", 
      glow && "shadow-[0_0_20px_rgba(59,130,246,0.15)] dark:shadow-[0_0_20px_rgba(59,130,246,0.1)] border-blue-200/80 dark:border-blue-900/50", 
      className
    )}>
      {children}
    </div>
  );
}

export function CardHeader({ 
  children, 
  className = "" 
}: { 
  children: React.ReactNode; 
  className?: string 
}) {
  return (
    <div className={cn(
      "flex items-center justify-between mb-5 pb-3 border-b border-slate-200/60 dark:border-gray-800/50", 
      className
    )}>
      {children}
    </div>
  );
}

export function CardTitle({ 
  children, 
  className = "" 
}: { 
  children: React.ReactNode; 
  className?: string 
}) {
  return (
    <h3 className={cn(
      "text-base font-bold text-slate-800 dark:text-white tracking-wide", 
      className
    )}>
      {children}
    </h3>
  );
}