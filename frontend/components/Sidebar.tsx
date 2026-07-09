"use client";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Cpu, Brain, Code2, Rocket, Activity, LogOut,
  PanelLeftClose, PanelLeftOpen
} from "lucide-react";

const nav = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard, color: "text-indigo-500", dot: "bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.8)]" },
  { href: "/devices", label: "Devices", icon: Cpu, color: "text-blue-500", dot: "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]" },
  { href: "/models", label: "Models", icon: Brain, color: "text-pink-500", dot: "bg-pink-500 shadow-[0_0_8px_rgba(236,72,153,0.8)]" },
  { href: "/scripts", label: "Scripts", icon: Code2, color: "text-orange-500", dot: "bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.8)]" },
  { href: "/deployments", label: "Deployments", icon: Rocket, color: "text-emerald-500", dot: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" },
  { href: "/monitoring", label: "Monitoring", icon: Activity, color: "text-purple-500", dot: "bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]" },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const path = usePathname();

  return (
    <aside className={cn(
      "fixed left-0 top-0 h-screen transition-all duration-300 flex flex-col",
      "z-30", // LOWERED from z-50 to z-30 so that modals and popups stay on top
      "bg-slate-100/85 dark:bg-gray-950/85 backdrop-blur-md",
      "border-r border-slate-200/60 dark:border-gray-800/50",
      // Responsive width: always w-56 on mobile, collapses to w-20 on desktop
      collapsed ? "w-56 md:w-20" : "w-56",
      // Responsive translate position: hidden off-screen on mobile when collapsed
      collapsed ? "-translate-x-full md:translate-x-0" : "translate-x-0"
    )}>

      {/* --- HORIZONTAL ARROW EXPANDER EDGE --- */}
      <div
        onClick={onToggle}
        className="absolute top-0 -right-2 w-4 h-full cursor-ew-resize z-50 hidden md:flex items-center justify-center group/edge"
      >
        <div className="w-1 h-12 rounded-full bg-blue-500/50 opacity-0 group-hover/edge:opacity-100 transition-opacity" />
      </div>
      {/* ---------------------------------------------- */}

      {/* Header */}
      <div className={cn(
        "h-16 border-b border-white dark:border-white transition-all flex flex-shrink-0 overflow-hidden relative z-40",
        collapsed ? "justify-center items-center" : "items-center justify-between px-5"
      )}>

        {collapsed ? (
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            className="relative group w-10 h-10 flex items-center justify-center rounded-xl hover:bg-transparent dark:hover:bg-transparent transition-colors cursor-pointer logo-collapsed-btn"
          >
            {/* Collapsed Logo */}
            <div className="absolute inset-0 flex items-center justify-center opacity-100 group-hover:opacity-0 transition-opacity duration-200">
              <div className="relative w-7 h-7 bg-transparent">
                <Image
                  src="/logo.png"
                  alt="Aura Platform"
                  fill
                  className="object-contain"
                  priority
                />
              </div>
            </div>

            {/* Expand Icon */}
            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-gray-500 dark:text-gray-400">
              <PanelLeftOpen size={20} />
            </div>

            {/* Tooltip */}
            <div className="absolute left-full ml-4 px-2.5 py-1.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-50 shadow-lg">
              Expand sidebar
            </div>
          </button>
        ) : (
          <>
            <div className="flex items-center gap-3 cursor-default">
              {/* Expanded Logo */}
              <div className="relative w-8 h-8 flex-shrink-0 bg-transparent">
                <Image
                  src="/logo.png"
                  alt="Aura Platform"
                  fill
                  className="object-contain"
                  priority
                />
              </div>
              <div className="whitespace-nowrap animate-fade-in">
                <p className="text-sm font-bold text-slate-800 dark:text-white tracking-tight">AURA</p>
                <p className="text-[10px] text-gray-500 dark:text-gray-400 font-mono tracking-wider">PLATFORM</p>
              </div>
            </div>

            <button
              onClick={(e) => { e.stopPropagation(); onToggle(); }}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
            >
              <PanelLeftClose size={18} />
            </button>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className={cn(
        "flex-1 px-3 py-6 flex flex-col gap-1.5 relative z-40",
        !collapsed && "overflow-y-auto scrollbar-hide"
      )}>
        {nav.map(({ href, label, icon: Icon, color, dot }) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={(e) => e.stopPropagation()}
              className={cn(
                "flex items-center rounded-xl text-sm transition-all duration-200 group relative cursor-pointer",
                collapsed ? "justify-center w-10 h-10 mx-auto" : "gap-3 px-3 py-2.5",
                active
                  ? "text-gray-900 dark:text-white font-semibold"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100/50 dark:hover:bg-gray-800/50 font-medium"
              )}
            >
              {active && (
                <div className="absolute inset-0 bg-white/80 dark:bg-gray-800/60 border border-slate-200/60 dark:border-gray-700/50 rounded-xl shadow-sm" />
              )}

              <Icon size={18} className={cn(
                "flex-shrink-0 relative z-10 transition-transform duration-200",
                active ? cn("scale-110", color) : "group-hover:scale-110 group-hover:text-gray-700 dark:group-hover:text-gray-300"
              )} />

              {!collapsed && <span className="relative z-10 whitespace-nowrap">{label}</span>}

              {active && !collapsed && (
                <div className={cn("ml-auto w-1.5 h-1.5 rounded-full relative z-10", dot)} />
              )}

              {/* Tooltip */}
              {collapsed && (
                <div className="absolute left-full ml-4 px-2.5 py-1.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-50 shadow-lg">
                  {label}
                </div>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer / Logout */}
      <div className="px-3 py-4 border-t border-white dark:border-white relative z-40">
        <button
          onClick={(e) => {
            e.stopPropagation();
            localStorage.removeItem("aura_token");
            document.cookie = "aura_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT;";
            window.location.href = "/";
          }}
          className={cn(
            "flex items-center rounded-xl text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 transition-all group relative cursor-pointer",
            collapsed ? "justify-center w-10 h-10 mx-auto" : "gap-3 px-3 py-2.5 w-full"
          )}
        >
          <LogOut size={18} className={cn("transition-transform", !collapsed && "group-hover:-translate-x-1")} />
          {!collapsed && <span>Sign out</span>}

          {/* Tooltip */}
          {collapsed && (
            <div className="absolute left-full ml-4 px-2.5 py-1.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-50 shadow-lg">
              Sign out
            </div>
          )}
        </button>
      </div>

    </aside>
  );
}