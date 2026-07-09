"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { cn, HW_LABELS } from "@/lib/utils";
import { api } from "@/lib/api";

const queryClient = new QueryClient({ 
  defaultOptions: { 
    queries: { refetchInterval: 10000, retry: 1 } 
  } 
});

function DynamicLabelsLoader() {
  const { data: labels } = useQuery({
    queryKey: ["hw-labels"],
    queryFn: async () => {
      try {
        const response = await api.get<Record<string, string>>("/api/devices/labels");
        return response.data;
      } catch {
        return {};
      }
    },
  });

  useEffect(() => {
    if (labels) {
      Object.assign(HW_LABELS, labels);
    }
  }, [labels]);

  return null;
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [hasToken, setHasToken] = useState<boolean | null>(null);

  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem("aura_token");
    if (!token) {
      setHasToken(false);
      router.push("/login");
    } else {
      setHasToken(true);
    }

    // Collapse sidebar by default on mobile screens
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setSidebarCollapsed(true);
    }
  }, [router]);

  if (!mounted || hasToken === null || hasToken === false) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <DynamicLabelsLoader />
      <div className="flex h-screen overflow-hidden bg-transparent dark:bg-gray-950">
        
        <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
        
        {/* Backdrop overlay for mobile screens when sidebar is expanded */}
        {!sidebarCollapsed && (
          <div 
            onClick={() => setSidebarCollapsed(true)}
            className="fixed inset-0 z-20 bg-slate-900/20 dark:bg-gray-950/40 backdrop-blur-[2px] md:hidden transition-all duration-300 cursor-pointer"
          />
        )}
        
        <div className={cn(
          "flex-1 flex flex-col overflow-hidden relative transition-all duration-300",
          sidebarCollapsed ? "ml-0 md:ml-20" : "ml-0 md:ml-56"
        )}>
          <div className="z-10 flex flex-col h-full">
            <TopBar sidebarCollapsed={sidebarCollapsed} onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)} />
            <main className="flex-1 overflow-y-auto p-4 md:p-8 dot-grid scroll-smooth">
              {children}
            </main>
          </div>
        </div>

      </div>
    </QueryClientProvider>
  );
}