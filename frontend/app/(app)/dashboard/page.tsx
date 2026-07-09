"use client";
import { useQuery } from "@tanstack/react-query";
import { getDevices, getModels, getScripts, getDeployments, getMonitoringStates } from "@/lib/api";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusDot } from "@/components/ui/StatusDot";
import { StatBar } from "@/components/ui/StatBar";
import { Badge } from "@/components/ui/Badge";
import { fmtRelative } from "@/lib/utils";
import { Cpu, Brain, Code2, Rocket, Activity, AlertTriangle } from "lucide-react";
import Link from "next/link";

const STATUS_VARIANT: Record<string, any> = {
  running: "success",
  sent: "info",
  pending: "secondary",
  compiling: "warning",
  failed: "destructive",
  stopped: "destructive",
};

function StatCard({
  label, value, icon: Icon, href, iconColor,
}: { label: string; value: number; icon: React.ElementType; href: string; iconColor: string }) {
  return (
    <Link href={href}>
      <div className="p-6 bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:-translate-y-1 hover:border-blue-500 transition-all cursor-pointer group flex items-center justify-between">
        <div>
          <p className="text-3xl font-bold text-gray-900 dark:text-white mb-1">{value}</p>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</p>
        </div>
        <div className={`w-12 h-12 rounded-full flex items-center justify-center bg-white dark:bg-gray-800 shadow-sm group-hover:scale-110 transition-transform ${iconColor}`}>
          <Icon size={24} />
        </div>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { data: devices = [] } = useQuery({ queryKey: ["devices"], queryFn: getDevices, refetchInterval: 5000 });
  const { data: models = [] } = useQuery({ queryKey: ["models"], queryFn: getModels });
  const { data: scripts = [] } = useQuery({ queryKey: ["scripts"], queryFn: getScripts });
  const { data: deployments = [] } = useQuery({ queryKey: ["deployments"], queryFn: getDeployments });
  const { data: states = [] } = useQuery({ queryKey: ["monitoring"], queryFn: getMonitoringStates, refetchInterval: 5000 });

  const online = devices.filter((d: any) => d.status === "online").length;
  const running = deployments.filter((d: any) => d.status === "running").length;
  const failed = deployments.filter((d: any) => d.status === "failed").length;

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500 mb-2 pb-1">
            Dashboard Overview
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Monitor your IoT Edge AI deployments and device telemetry in real-time.
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Devices" value={devices.length} icon={Cpu} href="/devices" iconColor="text-blue-500" />
        <StatCard label="Models" value={models.length} icon={Brain} href="/models" iconColor="text-pink-500" />
        <StatCard label="Scripts" value={scripts.length} icon={Code2} href="/scripts" iconColor="text-orange-500" />
        <StatCard label="Deployments" value={deployments.length} icon={Rocket} href="/deployments" iconColor="text-emerald-500" />
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Online devices", value: `${online} / ${devices.length}`, status: "online", color: "text-emerald-600 dark:text-emerald-400" },
          { label: "Running deployments", value: running, status: "running", color: "text-blue-600 dark:text-blue-400" },
          { label: "Failed deployments", value: failed, status: failed > 0 ? "failed" : "ready", color: failed > 0 ? "text-red-600 dark:text-red-400" : "text-gray-500" },
        ].map((item, i) => (
          <div key={i} className="p-5 bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              {item.status === "failed" && failed > 0
                ? <AlertTriangle size={14} className="text-red-500" />
                : <StatusDot status={item.status} />}
              <span className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{item.label}</span>
            </div>
            <p className={`text-2xl font-bold ${item.color}`}>{item.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live telemetry */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>Live Device Telemetry</CardTitle>
            <div className="flex items-center gap-3">
              <Activity size={18} className="text-blue-500 animate-pulse" />
              <Link href="/monitoring" className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline">View all</Link>
            </div>
          </CardHeader>
          <div className="space-y-6 mt-4">
            {states.length === 0 ? (
              <p className="text-sm text-gray-500 p-4 italic">
                No telemetry data received. Ensure devices are online and connected.
              </p>
            ) : (
              states.slice(0, 3).map((s: any) => (
                <div key={s.device_id} className="border-b border-gray-100 dark:border-gray-800/50 pb-4 last:border-0 last:pb-0">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <StatusDot status={s.status} />
                      <span className="text-sm font-bold text-gray-900 dark:text-white font-mono" title={s.device_id}>
                        {devices.find((d: any) => d.id === s.device_id)?.name || s.device_id}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">{fmtRelative(s.last_seen_at)}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <StatBar value={s.cpu_percent} label="CPU" color={s.cpu_percent > 80 ? "red-500" : "blue-500"} />
                    <StatBar value={s.ram_percent} label="RAM" color={s.ram_percent > 80 ? "orange-500" : "emerald-500"} />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Recent deployments */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Deployments</CardTitle>
            <Link href="/deployments" className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline">
              View all
            </Link>
          </CardHeader>
          <div className="space-y-1">
            {deployments.length === 0 ? (
              <p className="text-sm text-gray-500 p-4 italic">
                No recent deployments. Navigate to deployments to create one.
              </p>
            ) : (
              deployments.slice(0, 5).map((d: any) => (
                <div key={d.id} className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-800/50 last:border-0">
                  <div className="flex items-center gap-3">
                    <StatusDot status={d.status} />
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate max-w-[180px]">{d.name || `${d.id.slice(0, 8)}…`}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={STATUS_VARIANT[d.status] || "default"}>
                      {d.status}
                    </Badge>
                    <span className="text-xs text-gray-400 font-mono">{fmtRelative(d.created_at)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
