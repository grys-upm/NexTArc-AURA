"use client";
import { useQuery } from "@tanstack/react-query";
import { getMonitoringStates, getDevices } from "@/lib/api";
import Link from "next/link";
import { EdgeMap } from "@/components/monitoring/EdgeMap";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatBar } from "@/components/ui/StatBar";
import { StatusDot } from "@/components/ui/StatusDot";
import { Badge } from "@/components/ui/Badge";
import { fmtRelative } from "@/lib/utils";
import { Activity, ShieldAlert, Wifi, MemoryStick } from "lucide-react";

export default function MonitoringPage() {
  const { data: states = [] } = useQuery({
    queryKey: ["monitoring"],
    queryFn: getMonitoringStates,
    refetchInterval: 5000,
  });

  const { data: devices = [] } = useQuery({
    queryKey: ["devices"],
    queryFn: getDevices,
  });

  // Filter telemetry states to only include devices that actually exist in the registered devices list
  const activeStates = states.filter((s: any) =>
    devices.some((d: any) => d.id === s.device_id)
  );

  const stats = {
    activeNodes: `${activeStates.filter((s: any) => s.status === "online").length} / ${activeStates.length || 0}`,
    avgLatency: (() => {
      const validLatencies = activeStates
        .filter((s: any) => s.status === "online" && typeof s.latency_ms === "number" && s.latency_ms >= 0)
        .map((s: any) => s.latency_ms);
      if (validLatencies.length === 0) return "— ms";
      const sum = validLatencies.reduce((acc: number, val: number) => acc + val, 0);
      return `${(sum / validLatencies.length).toFixed(5)} ms`;
    })(),
    alerts: activeStates.filter((s: any) => s.cpu_percent > 90).length,
    cpuLoad: activeStates.length > 0
      ? Math.round(activeStates.reduce((acc: number, s: any) => acc + s.cpu_percent, 0) / activeStates.length)
      : 0,
    memory: activeStates.length > 0
      ? Math.round(activeStates.reduce((acc: number, s: any) => acc + s.ram_percent, 0) / activeStates.length)
      : 0,
  };

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500 mb-2 pb-1">
            Device Set Monitoring
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Real-time health status, node telemetry and physical mapping.
          </p>
        </div>
      </div>

      {/* Grid containing overview stats */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          { label: "Active Gateways", value: stats.activeNodes, icon: Wifi, color: "text-blue-500" },
          { label: "Avg Node Latency", value: stats.avgLatency, icon: Activity, color: "text-pink-500" },
          { label: "Critical Alerts", value: stats.alerts, icon: ShieldAlert, color: stats.alerts > 0 ? "text-red-500 animate-pulse" : "text-gray-400" },
        ].map((stat, i) => {
          const Icon = stat.icon;
          return (
            <div key={i} className="p-6 bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{stat.value}</p>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{stat.label}</p>
              </div>
              <div className={`w-12 h-12 rounded-full flex items-center justify-center bg-white dark:bg-gray-800 shadow-sm ${stat.color}`}>
                <Icon size={22} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Map */}
        <div className="lg:col-span-7 flex flex-col relative w-full">
          <EdgeMap states={activeStates} />
        </div>

        {/* Right Column: Node details list */}
        {activeStates.length === 0 ? (
          <div className="lg:col-span-5 border border-dashed border-2 bg-transparent shadow-none opacity-60 rounded-3xl p-6 text-center italic text-gray-500">
            No active telemetry connections reported.
          </div>
        ) : (
          <Card className="lg:col-span-5 h-[500px] overflow-y-auto">
            <CardHeader className="mb-4">
              <CardTitle>Connected IoT Edge Devices</CardTitle>
            </CardHeader>
            <div className="space-y-4 px-4 pb-4">
              {activeStates.map((s: any) => (
                <div key={s.device_id} className="p-4 bg-gray-50 dark:bg-gray-900/40 border border-gray-150 dark:border-gray-850 rounded-2xl space-y-3">
                  <div className="flex justify-between items-start">
                    <Link href={`/devices/${s.device_id}?from=monitoring`} className="hover:underline">
                      <h4 className="font-bold text-sm text-gray-900 dark:text-white truncate max-w-[200px]">
                        {devices.find((d: any) => d.id === s.device_id)?.name || s.device_id}
                      </h4>
                    </Link>
                    <div className="flex items-center gap-2">
                      <StatusDot status={s.status} />
                      <Badge variant="muted" className="font-mono text-[9px] uppercase">{s.status}</Badge>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <StatBar value={s.cpu_percent} label="CPU" color={s.cpu_percent > 80 ? "red-500" : "blue-500"} />
                    <StatBar value={s.ram_percent} label="RAM" color={s.ram_percent > 80 ? "orange-500" : "emerald-500"} />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">{fmtRelative(s.last_seen_at)}</p>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Global Edge Resources: two separate stat cards with progress bars */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="p-6 bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{stats.cpuLoad}%</p>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Aggregated CPU Load</p>
            </div>
            <div className="w-12 h-12 rounded-full flex items-center justify-center bg-white dark:bg-gray-800 shadow-sm text-blue-500">
              <Activity size={22} />
            </div>
          </div>
          <StatBar value={stats.cpuLoad} color="blue-500" unit="%" />
        </div>

        <div className="p-6 bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{stats.memory}%</p>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Global Memory Usage</p>
            </div>
            <div className="w-12 h-12 rounded-full flex items-center justify-center bg-white dark:bg-gray-800 shadow-sm text-orange-500">
              <MemoryStick size={22} />
            </div>
          </div>
          <StatBar value={stats.memory} color="orange-500" unit="%" />
        </div>
      </div>
    </div>
  );
}
