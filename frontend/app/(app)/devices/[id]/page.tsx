"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getDevice,
  getDeviceState,
  getInferenceResults,
  updateDevice,
  getDeployments,
  getModels,
  getScripts
} from "@/lib/api";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatBar } from "@/components/ui/StatBar";
import { StatusDot } from "@/components/ui/StatusDot";
import { HW_LABELS, fmtRelative } from "@/lib/utils";
import { DeviceMiniMap } from "@/components/monitoring/DeviceMiniMap";
import {
  ArrowLeft, Cpu, Layers, Radio, Zap, Server, Activity, Edit2, Check,
  Play, Info, Camera, Thermometer, Ruler, Compass, Power, Disc,
  Volume2, Lightbulb, RefreshCw, Clock, Wifi, MemoryStick
} from "lucide-react";

const CATEGORY_ICONS: Record<string, any> = {
  camera: Camera,
  temperature: Thermometer,
  distance: Ruler,
  imu: Compass,
  relay: Power,
  servo: Disc,
  buzzer: Volume2,
  led: Lightbulb,
};

const STATUS_VARIANT: Record<string, any> = {
  running: "success",
  sent: "info",
  pending: "secondary",
  compiling: "warning",
  failed: "destructive",
  stopped: "destructive",
};

const getPeripheralIcon = (name: string, defaultIcon: any) => {
  const parts = name.split("/");
  const category = parts.length > 1 ? parts[0] : "";
  return CATEGORY_ICONS[category] || defaultIcon;
};

export default function DeviceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const from = searchParams.get("from");

  let backLabel = "Back to Devices";
  let backUrl = "/devices";

  if (from === "monitoring") {
    backLabel = "Back to Monitoring";
    backUrl = "/monitoring";
  } else if (from === "deployments") {
    backLabel = "Back to Deployments";
    backUrl = "/deployments";
  }

  const qc = useQueryClient();

  const deviceId = params.id as string;

  const [isEditingName, setIsEditingName] = useState(false);
  const [editingName, setEditingName] = useState("");

  // Query Device Info
  const { data: device, isLoading: loadingDevice, error: deviceError } = useQuery({
    queryKey: ["device-detail", deviceId],
    queryFn: () => getDevice(deviceId),
    enabled: !!deviceId,
  });

  // Query Device Telemetry
  const { data: deviceState, isLoading: loadingState } = useQuery({
    queryKey: ["device-detail-state", deviceId],
    queryFn: () => getDeviceState(deviceId),
    enabled: !!deviceId,
    refetchInterval: 5000, // telemetry refresh every 5s
  });

  // Query Deployments, Models, and Scripts for names
  const { data: deployments = [] } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchInterval: 5000,
  });
  const { data: models = [] } = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
  });
  const { data: scripts = [] } = useQuery({
    queryKey: ["scripts"],
    queryFn: getScripts,
  });

  // Query Inference Results
  const { data: inferenceResults = [], isLoading: loadingInference } = useQuery({
    queryKey: ["device-detail-inference", deviceId],
    queryFn: () => getInferenceResults(deviceId, 30),
    enabled: !!deviceId && deviceState?.status === "online",
    refetchInterval: 2000, // inference updates every 2s
  });

  // Update Name Mutation
  const updateDeviceMutation = useMutation({
    mutationFn: (name: string) => updateDevice(deviceId, { name }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["device-detail", deviceId] });
      qc.invalidateQueries({ queryKey: ["devices"] });
      setIsEditingName(false);
    },
  });

  useEffect(() => {
    if (device) {
      setEditingName(device.name);
    }
  }, [device]);

  if (loadingDevice) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
        <RefreshCw className="animate-spin text-blue-500" size={32} />
        <p className="text-gray-500 dark:text-gray-400 text-sm">Loading device information...</p>
      </div>
    );
  }

  if (deviceError || !device) {
    return (
      <div className="max-w-md mx-auto mt-10">
        <Card className="border border-red-200 dark:border-red-900/50 p-6">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-950/30 flex items-center justify-center">
              <Info className="text-red-500" size={24} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">Device Not Found</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                The device with ID <span className="font-mono">{deviceId}</span> does not exist or you do not have permission to view it.
              </p>
            </div>
            <Button onClick={() => router.push("/devices")} variant="outline" className="w-full">
              Back to Devices
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const handleSaveName = () => {
    if (editingName.trim() && editingName !== device.name) {
      updateDeviceMutation.mutate(editingName.trim());
    } else {
      setIsEditingName(false);
    }
  };

  // Find deployment details
  const activeDeploymentId = deviceState?.active_deployment_id;
  let activeDeployment = activeDeploymentId
    ? deployments.find((d: any) => d.id === activeDeploymentId)
    : undefined;

  // Fallback: search for the latest deployment for this device in the deployments list
  if (!activeDeployment) {
    activeDeployment = deployments.find((d: any) => d.device_id === deviceId);
  }

  const activeModel = activeDeployment && models.find((m: any) => m.id === activeDeployment.model_id);
  const activeScript = activeDeployment && scripts.find((s: any) => s.id === activeDeployment.script_id);

  const status = deviceState?.status || device.status || "offline";

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      {/* Header with Navigation */}
      <div className="flex flex-col gap-4">
        <button
          onClick={() => router.push(backUrl)}
          className="flex items-center gap-2 text-sm font-semibold text-gray-500 hover:text-blue-500 dark:text-gray-400 dark:hover:text-blue-400 transition-colors w-fit group"
        >
          <ArrowLeft size={16} className="transform group-hover:-translate-x-1 transition-transform" />
          {backLabel}
        </button>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-200 dark:border-gray-800 pb-6">
          <div className="flex items-center gap-4 flex-1">
            <div className="p-4 bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 dark:from-blue-500/20 dark:to-indigo-500/20 rounded-2xl border border-blue-500/20">
              <Cpu size={32} className="text-blue-500" />
            </div>
            <div className="flex-1 min-w-0">
              {isEditingName ? (
                <div className="flex items-center gap-2 max-w-md">
                  <Input
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    className="h-10 text-xl font-bold bg-white dark:bg-gray-900"
                    placeholder="Enter device name..."
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveName();
                      if (e.key === "Escape") {
                        setEditingName(device.name);
                        setIsEditingName(false);
                      }
                    }}
                  />
                  <Button size="sm" onClick={handleSaveName} loading={updateDeviceMutation.isPending}>
                    <Check size={16} />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-2 group">
                  <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white truncate">
                    {device.name}
                  </h1>
                  <button
                    onClick={() => setIsEditingName(true)}
                    className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                    title="Edit Name"
                  >
                    <Edit2 size={16} />
                  </button>
                </div>
              )}

              <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                <Badge variant="default" className="font-semibold uppercase tracking-wider text-[10px]">
                  {HW_LABELS[device.hardware_type] || device.hardware_type}
                </Badge>
                <span className="text-xs text-gray-400 font-mono">ID: {device.id}</span>
                <span className="text-xs text-gray-400 font-mono">• Registered {fmtRelative(device.created_at)}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 self-start md:self-center shrink-0">
            <span className="text-sm font-semibold text-gray-500 dark:text-gray-400">Status:</span>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-bold uppercase tracking-wider ${
              status === "online"
                ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800/50 shadow-[0_0_15px_rgba(16,185,129,0.1)]"
                : "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/20 dark:text-red-400 dark:border-red-900/30 shadow-[0_0_15px_rgba(239,68,68,0.05)]"
            }`}>
              <StatusDot status={status} />
              {status}
            </div>
          </div>
        </div>
      </div>

      {/* Main Responsive Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Column 1: Specs & Peripherals (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          <Card className="h-full flex flex-col justify-between">
            <div>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Layers size={18} className="text-blue-500" />
                  See more
                </CardTitle>
              </CardHeader>
              
              <div className="space-y-6 mt-4">
                {/* Description / Base Layer */}
                <div>
                  <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1">Description / Base Layer</h4>
                  <p className="text-sm text-gray-900 dark:text-white font-bold mb-1">
                    {HW_LABELS[device.hardware_type] || device.hardware_type}
                  </p>
                  {device.description ? (
                    <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                      {device.description}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-400 dark:text-gray-500 italic">
                      No additional description provided.
                    </p>
                  )}
                </div>

                {/* Peripherals */}
                <div className="space-y-3">
                  <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">Attached Peripherals</h4>
                  
                  {/* Sensors */}
                  <div className="space-y-2">
                    <span className="text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider block">Sensors</span>
                    {device.sensors && device.sensors.length > 0 ? (
                      device.sensors.map((s: string, idx: number) => {
                        const Icon = getPeripheralIcon(s, Radio);
                        return (
                          <div key={idx} className="flex justify-between items-center p-2.5 bg-slate-50 dark:bg-gray-800/40 border border-slate-200/50 dark:border-gray-800/50 rounded-xl text-sm transition-all hover:bg-slate-100 dark:hover:bg-gray-800/60">
                            <span className="flex items-center gap-2 text-gray-700 dark:text-gray-200 font-medium">
                              <Icon size={16} className="text-emerald-500" />
                              {HW_LABELS[s] || s}
                            </span>
                            <Badge variant="success" className="text-[9px]">Sensor</Badge>
                          </div>
                        );
                      })
                    ) : (
                      <p className="text-xs text-gray-400 dark:text-gray-500 italic px-1">No sensor peripherals linked.</p>
                    )}
                  </div>

                  {/* Actuators */}
                  <div className="space-y-2 pt-2">
                    <span className="text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider block">Actuators</span>
                    {device.actuators && device.actuators.length > 0 ? (
                      device.actuators.map((a: string, idx: number) => {
                        const Icon = getPeripheralIcon(a, Zap);
                        return (
                          <div key={idx} className="flex justify-between items-center p-2.5 bg-slate-50 dark:bg-gray-800/40 border border-slate-200/50 dark:border-gray-800/50 rounded-xl text-sm transition-all hover:bg-slate-100 dark:hover:bg-gray-800/60">
                            <span className="flex items-center gap-2 text-gray-700 dark:text-gray-200 font-medium">
                              <Icon size={16} className="text-yellow-500" />
                              {HW_LABELS[a] || a}
                            </span>
                            <Badge variant="warning" className="text-[9px]">Actuator</Badge>
                          </div>
                        );
                      })
                    ) : (
                      <p className="text-xs text-gray-400 dark:text-gray-500 italic px-1">No actuator peripherals linked.</p>
                    )}
                  </div>

                  {/* Others */}
                  <div className="space-y-2 pt-2">
                    <span className="text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider block">Other Components</span>
                    {device.others && device.others.length > 0 ? (
                      device.others.map((o: string, idx: number) => {
                        const Icon = getPeripheralIcon(o, Server);
                        return (
                          <div key={idx} className="flex justify-between items-center p-2.5 bg-slate-50 dark:bg-gray-800/40 border border-slate-200/50 dark:border-gray-800/50 rounded-xl text-sm transition-all hover:bg-slate-100 dark:hover:bg-gray-800/60">
                            <span className="flex items-center gap-2 text-gray-700 dark:text-gray-200 font-medium">
                              <Icon size={16} className="text-blue-500" />
                              {HW_LABELS[o] || o}
                            </span>
                            <Badge variant="default" className="text-[9px]">Other</Badge>
                          </div>
                        );
                      })
                    ) : (
                      <p className="text-xs text-gray-400 dark:text-gray-500 italic px-1">No other components linked.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {deviceState?.last_seen_at && (
              <div className="border-t border-gray-200 dark:border-gray-800 pt-4 mt-6 flex items-center justify-between text-xs text-gray-400">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  Last telemetry update:
                </span>
                <span className="font-mono text-gray-500 dark:text-gray-300">
                  {new Date(deviceState.last_seen_at).toLocaleTimeString()}
                </span>
              </div>
            )}
          </Card>
        </div>

        {/* Column 2: Telemetry & active deployment (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Telemetry Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity size={18} className="text-blue-500" />
                Live Telemetry
              </CardTitle>
            </CardHeader>

            <div className="space-y-6 mt-4">
              {status === "online" && deviceState ? (
                <>
                  <div className="space-y-4">
                    <StatBar
                      label="CPU Load"
                      value={deviceState.cpu_percent}
                      color={deviceState.cpu_percent > 80 ? "red-500" : "blue-500"}
                    />
                    <StatBar
                      label="RAM Memory Usage"
                      value={deviceState.ram_percent}
                      color={deviceState.ram_percent > 80 ? "orange-500" : "emerald-500"}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4 border-t border-slate-100 dark:border-gray-800/60 pt-4">
                    <div className="bg-slate-50 dark:bg-gray-800/30 border border-slate-200/40 dark:border-gray-800/40 p-3 rounded-xl">
                      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1">RAM USED</span>
                      <div className="flex items-center gap-1.5 text-gray-800 dark:text-white font-bold text-lg">
                        <MemoryStick size={16} className="text-emerald-500" />
                        {deviceState.ram_used_mb?.toFixed ? deviceState.ram_used_mb.toFixed(0) : deviceState.ram_used_mb} MB
                      </div>
                    </div>

                    <div className="bg-slate-50 dark:bg-gray-800/30 border border-slate-200/40 dark:border-gray-800/40 p-3 rounded-xl">
                      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1">LATENCY</span>
                      <div className="flex items-center gap-1.5 text-gray-800 dark:text-white font-bold text-lg">
                        <Wifi size={16} className="text-blue-500" />
                        {typeof deviceState.latency_ms === "number" ? deviceState.latency_ms.toFixed(5) : deviceState.latency_ms} ms
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-10 border border-dashed rounded-2xl flex flex-col items-center justify-center space-y-3 bg-slate-50/50 dark:bg-gray-900/10">
                  <Wifi size={28} className="text-gray-300 dark:text-gray-700" />
                  <div>
                    <p className="text-sm font-bold text-gray-500 dark:text-gray-400">Telemetry Offline</p>
                    <p className="text-xs text-gray-400 max-w-[200px] mx-auto mt-1">
                      Start the device agent or connect the device to retrieve telemetry.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Active Deployment Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server size={18} className="text-blue-500" />
                Active Deployment
              </CardTitle>
            </CardHeader>

            <div className="mt-4">
              {activeDeployment ? (
                <div className="space-y-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-bold text-gray-900 dark:text-white text-base">
                        {activeDeployment.name || `Deployment ${activeDeployment.id.slice(0, 8)}`}
                      </h3>
                      <p className="text-xs text-gray-400 font-mono mt-0.5">ID: {activeDeployment.id.slice(0, 8)}</p>
                    </div>
                    <Badge variant={STATUS_VARIANT[activeDeployment.status] || "default"} className="font-bold tracking-wider uppercase text-[9px]">
                      {activeDeployment.status}
                    </Badge>
                  </div>

                  <div className="space-y-3 bg-slate-50 dark:bg-gray-800/40 p-4 rounded-xl border border-slate-200/50 dark:border-gray-800/50">
                    <div>
                      <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider block">Deployed Model</span>
                      <span className="text-sm font-semibold text-gray-800 dark:text-slate-200 break-all">
                        {activeModel?.name || activeDeployment.model_id}
                      </span>
                    </div>

                    <div className="border-t border-slate-200/40 dark:border-gray-700/40 pt-2">
                      <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider block">Inference Script</span>
                      <span className="text-sm font-semibold text-gray-800 dark:text-slate-200 break-all">
                        {activeScript?.name || activeDeployment.script_id}
                      </span>
                    </div>
                  </div>

                  {activeDeployment.error_msg && (
                    <div className="bg-red-50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/30 rounded-xl p-3">
                      <span className="text-[9px] font-bold text-red-500 uppercase tracking-wider block">Deployment Error</span>
                      <p className="text-xs text-red-650 dark:text-red-400 font-mono mt-1 whitespace-pre-wrap">{activeDeployment.error_msg}</p>
                    </div>
                  )}

                  <div className="text-[10px] text-gray-400 font-mono flex items-center justify-between">
                    <span>Deployed:</span>
                    <span>{fmtRelative(activeDeployment.created_at)}</span>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 border border-dashed rounded-2xl flex flex-col items-center justify-center space-y-3 bg-slate-50/50 dark:bg-gray-900/10">
                  <Play size={28} className="text-gray-300 dark:text-gray-700" />
                  <div>
                    <p className="text-sm font-bold text-gray-500 dark:text-gray-400">No Active Deployment</p>
                    <p className="text-xs text-gray-400 max-w-[220px] mx-auto mt-1">
                      No model or inference script is currently deployed to this device.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Geospatial Deployment Map */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2">
                <Compass size={18} className="text-blue-500" />
                Geospatial Location
              </CardTitle>
            </CardHeader>
            <div className="mt-2">
              <DeviceMiniMap coordinates={deviceState?.coordinates} status={status} />
            </div>
          </Card>
        </div>

        {/* Column 3: Live Inference Stream (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          <Card className="h-full flex flex-col">
            <CardHeader className="shrink-0">
              <div className="flex items-center justify-between w-full">
                <CardTitle className="flex items-center gap-2">
                  <Activity size={18} className="text-blue-500 animate-pulse" />
                  Live Inference Stream
                </CardTitle>
                <Badge variant="muted" className="font-mono text-[9px] scale-90 origin-right">
                  2s POLLING
                </Badge>
              </div>
            </CardHeader>

            <div className="flex-1 overflow-y-auto mt-4 pr-1 min-h-[350px] max-h-[600px] space-y-3 scrollbar-thin">
              {loadingInference ? (
                <div className="text-center py-10 text-xs text-gray-400 italic">
                  Fetching prediction streams...
                </div>
              ) : status !== "online" ? (
                <div className="text-center py-16 flex flex-col items-center justify-center space-y-3 px-4">
                  <Play size={32} className="text-gray-350 dark:text-gray-650" />
                  <p className="text-sm font-bold text-gray-500 dark:text-gray-400">Device is Offline</p>
                  <p className="text-xs text-gray-400 text-center max-w-xs">
                    Inference streams are only captured from active devices running AI tasks.
                  </p>
                </div>
              ) : inferenceResults.length === 0 ? (
                <div className="text-center py-16 border border-dashed rounded-2xl flex flex-col items-center justify-center space-y-3 bg-slate-50/50 dark:bg-gray-900/10 mx-2">
                  <Play size={28} className="text-gray-350 dark:text-gray-650" />
                  <p className="text-sm font-bold text-gray-500 dark:text-gray-400">No predictions recorded</p>
                  <p className="text-xs text-gray-400 text-center max-w-[200px] mx-auto">
                    Verify that the edge agent has started running the deployment script.
                  </p>
                </div>
              ) : (
                inferenceResults.map((result: any, idx: number) => {
                  let parsedResult: any = [];
                  try {
                    parsedResult = JSON.parse(result.result_json);
                  } catch (e) {
                    parsedResult = result.result_json;
                  }

                  const detections = Array.isArray(parsedResult)
                    ? parsedResult
                    : parsedResult && typeof parsedResult === "object"
                    ? Object.entries(parsedResult).map(([k, v]) => ({ class: k, value: v }))
                    : [];

                  const hasDetections = detections.length > 0;

                  return (
                    <div
                      key={idx}
                      className="p-3.5 border border-slate-200/50 dark:border-gray-800/80 bg-slate-50/50 dark:bg-gray-900/40 rounded-xl shadow-sm space-y-2 transition-all hover:bg-slate-100/50 dark:hover:bg-gray-900/60"
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-bold font-mono text-gray-400 flex items-center gap-1">
                          <Clock size={11} />
                          {new Date(result.timestamp).toLocaleTimeString()}
                        </span>
                        <span className="text-gray-400 font-mono text-[9px] bg-slate-100 dark:bg-gray-850 px-1.5 py-0.5 rounded">
                          dep: {result.deployment_id?.slice(0, 8) || "—"}
                        </span>
                      </div>

                      {hasDetections ? (
                        <div className="grid grid-cols-1 gap-1.5">
                          {detections.map((det: any, dIdx: number) => (
                            <div
                              key={dIdx}
                              className="flex items-center justify-between p-2 rounded-lg bg-white dark:bg-gray-950 border border-slate-150 dark:border-gray-800/80 text-xs shadow-inner"
                            >
                              <span className="font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1">
                                {det.class}
                              </span>
                              {det.confidence !== undefined ? (
                                <Badge variant="success" className="text-[10px] font-bold">
                                  {Math.round(det.confidence * 100)}%
                                </Badge>
                              ) : det.value !== undefined ? (
                                <span className="font-mono text-blue-500 font-bold truncate max-w-[120px]">
                                  {typeof det.value === "object" ? JSON.stringify(det.value) : String(det.value)}
                                </span>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-400 dark:text-gray-500 italic pl-1">
                          No targets detected in this frame.
                        </p>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </Card>
        </div>

      </div>
    </div>
  );
}
