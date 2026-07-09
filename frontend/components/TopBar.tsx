"use client";
import { usePathname } from "next/navigation";
import { StatusDot } from "@/components/ui/StatusDot";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Menu } from "lucide-react";

const TITLES: Record<string, string> = {
  "/dashboard": "Overview",
  "/devices": "Devices",
  "/models": "Models",
  "/scripts": "Scripts",
  "/deployments": "Deployments",
  "/monitoring": "Monitoring",
};

interface TopBarProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}

export function TopBar({ sidebarCollapsed, onToggleSidebar }: TopBarProps) {
  const path = usePathname();
  const title = Object.entries(TITLES).find(([k]) => path.startsWith(k))?.[1] || "AURA Platform";

  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Prevent hydration mismatch by only rendering the toggle after the client has mounted
  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <header className={cn(
      "sticky top-0 z-40 flex h-16 w-full items-center justify-between",
      "bg-slate-100/60 dark:bg-gray-950/40 backdrop-blur-xl", // Frosted glass effect
      "border-b border-slate-200/60 dark:border-gray-800/50", // Soft matte border
      "px-4 md:px-8 transition-all duration-300"
    )}>
      <div className="flex items-center">
        {/* Hamburger Menu Button for mobile screens */}
        <button
          onClick={onToggleSidebar}
          className="p-2 mr-3 rounded-xl border border-slate-200 dark:border-gray-800 hover:bg-slate-100/80 dark:hover:bg-gray-800/80 transition-colors md:hidden text-gray-700 dark:text-gray-300 cursor-pointer"
          aria-label="Toggle Sidebar"
        >
          <Menu size={18} />
        </button>
        <h1 className="text-sm font-bold text-gray-900 dark:text-white tracking-wide uppercase">
          {title}
        </h1>
      </div>

      <div className="flex-1" />

      {/* Theme Toggle Button */}
      {mounted && (
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Toggle Dark Mode"
        >
          {theme === "dark" ? (
            // Sun Icon
            <svg className="w-4 h-4 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4.22 2.32a1 1 0 011.415 0l.708.708a1 1 0 01-1.414 1.415l-.708-.708a1 1 0 010-1.415zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zm-2.32 4.22a1 1 0 010 1.415l-.708.708a1 1 0 01-1.414-1.415l.708-.708a1 1 0 011.415 0zM10 18a1 1 0 01-1-1v-1a1 1 0 112 0v1a1 1 0 01-1 1zm-4.22-2.32a1 1 0 01-1.415 0l-.708-.708a1 1 0 011.414-1.415l.708.708a1 1 0 010 1.415zM2 10a1 1 0 011-1h1a1 1 0 110 2H3a1 1 0 01-1-1zm2.32-4.22a1 1 0 010-1.415l.708-.708a1 1 0 011.414 1.415l-.708.708a1 1 0 01-1.415 0zM10 5a5 5 0 100 10 5 5 0 000-10z" clipRule="evenodd"></path>
            </svg>
          ) : (
            // Moon Icon
            <svg className="w-4 h-4 text-gray-700" fill="currentColor" viewBox="0 0 20 20">
              <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path>
            </svg>
          )}
        </button>
      )}

    </header>
  );
}