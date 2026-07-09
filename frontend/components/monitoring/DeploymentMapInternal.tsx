"use client";
import React, { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useTheme } from "next-themes";
import { useQuery } from "@tanstack/react-query";
import { getInferenceResults } from "@/lib/api";
import { MapPin } from "lucide-react";
import { useRouter } from "next/navigation";

interface DeploymentMapInternalProps {
  states?: any[];
  deployments?: any[];
  devices?: any[];
  models?: any[];
  scripts?: any[];
}

const createTacticalIcon = (status: string, isDark: boolean) => {
  const shadowOpacity = isDark ? "0.5" : "0.7"; 
  
  let colorClass = `bg-blue-500 text-blue-500 shadow-[0_0_15px_rgba(59,130,246,${shadowOpacity})]`;
  if (status === "warning") colorClass = `bg-yellow-500 text-yellow-500 shadow-[0_0_15px_rgba(234,179,8,${shadowOpacity})]`;
  if (status === "offline") colorClass = `bg-red-500 text-red-500 shadow-[0_0_15px_rgba(239,68,68,${shadowOpacity})]`;

  const isOffline = status === "offline";

  const htmlString = `
    <div class="relative flex items-center justify-center w-full h-full cursor-pointer">
      ${!isOffline ? `
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div class="w-8 h-8 rounded-full border border-current absolute animate-ping opacity-30 ${colorClass}"></div>
          <div class="w-12 h-12 rounded-full border border-current absolute animate-ping opacity-10 [animation-delay:0.5s] ${colorClass}"></div>
        </div>
      ` : ''}
      <div class="w-3 h-3 rounded-full ${colorClass} relative z-10 border border-white/20"></div>
    </div>
  `;

  return L.divIcon({
    html: htmlString,
    className: "transparent-leaflet-icon",
    iconSize: [48, 48],
    iconAnchor: [24, 24],
  });
};

export default function DeploymentMapInternal({
  states = [],
  deployments = [],
  devices = [],
  models = [],
  scripts = []
}: DeploymentMapInternalProps) {
  const { theme, systemTheme } = useTheme();
  const [activeNode, setActiveNode] = useState<any | null>(null);
  const [markers, setMarkers] = useState<any[]>([]);
  const router = useRouter();

  const currentTheme = theme === "system" ? systemTheme : theme;
  const isDark = currentTheme === "dark";

  const tileUrl = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

  useEffect(() => {
    const realMarkers = states
      .filter(s => s.coordinates && s.coordinates.length === 2)
      .map(s => {
        const device = devices.find((d: any) => d.id === s.device_id);
        return {
          id: s.device_id,
          name: device ? device.name : s.device_id,
          status: s.status,
          coordinates: [s.coordinates[1], s.coordinates[0]], 
        };
      });
    setMarkers(realMarkers);
  }, [states, devices]);

  // Query live inference results for the activeNode (hovered/selected device)
  const { data: inferenceResults = [], isLoading: loadingInference } = useQuery({
    queryKey: ["device-inference-map", activeNode?.id],
    queryFn: () => getInferenceResults(activeNode.id, 1),
    enabled: !!activeNode,
    refetchInterval: activeNode ? 2000 : false,
  });

  if (markers.length === 0) {
    return (
      <div className="w-full h-full bg-gray-50 dark:bg-slate-900 rounded-3xl border border-gray-200 dark:border-slate-800 p-8 relative overflow-hidden flex items-center justify-center">
        <div className="flex flex-col items-center text-center max-w-sm space-y-3 z-10">
          <div className="w-12 h-12 rounded-xl bg-gray-100 dark:bg-slate-800/50 flex items-center justify-center border border-gray-200 dark:border-slate-700">
            <MapPin size={24} className="text-gray-400 dark:text-gray-500" />
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-700 dark:text-gray-300">No Geolocation Data</h3>
            <p className="text-xs text-gray-500 mt-1">No active edge nodes are reporting spatial coordinates in this environment.</p>
          </div>
        </div>
      </div>
    );
  }

  const defaultCenter: [number, number] = markers.length > 0 
    ? markers[0].coordinates 
    : [40.4168, -3.7038];

  // Resolve deployment characteristics for active tooltip
  const activeDeviceState = activeNode ? states.find((s: any) => s.device_id === activeNode.id) : null;
  
  // Try to find the deployment reported by the edge agent telemetry first
  let activeDeployment = activeDeviceState && activeDeviceState.active_deployment_id
    ? deployments.find((d: any) => d.id === activeDeviceState.active_deployment_id)
    : undefined;
  
  // Fallback: search for the latest deployment for this device in the deployments list
  if (!activeDeployment && activeNode) {
    activeDeployment = deployments.find((d: any) => d.device_id === activeNode.id);
  }

  const activeModel = activeDeployment && models.find((m: any) => m.id === activeDeployment.model_id);
  const activeScript = activeDeployment && scripts.find((s: any) => s.id === activeDeployment.script_id);

  return (
    <div className="w-full h-full bg-gray-100 dark:bg-slate-900 rounded-3xl border border-gray-200 dark:border-slate-800 relative overflow-hidden flex flex-col z-0">
      
      <div className="absolute top-6 left-6 z-[1000] pointer-events-none">
        <h3 className="text-gray-900 dark:text-white font-bold text-lg flex items-center gap-2">
          <MapPin size={18} className="text-blue-500"/>
          Deployment Area Map
        </h3>
        <p className="text-gray-500 dark:text-slate-400 text-xs mt-1">Active deployment tracking and live inference outputs</p>
      </div>

      <MapContainer 
        center={defaultCenter} 
        zoom={13} 
        scrollWheelZoom={true} 
        className="w-full h-full !bg-transparent" 
        zoomControl={false}
      >
        <TileLayer
          key={isDark ? "dark" : "light"}
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
          url={tileUrl}
          className={isDark ? "dark-tactical-tiles" : ""}
        />

        {markers.map((marker) => (
          <Marker 
            key={marker.id} 
            position={marker.coordinates as [number, number]}
            icon={createTacticalIcon(marker.status, isDark)}
            eventHandlers={{
              mouseover: () => setActiveNode(marker),
              mouseout: () => setActiveNode(null),
              click: () => router.push(`/devices/${marker.id}?from=deployments`),
            }}
          />
        ))}
      </MapContainer>

      {/* Floating Deployment + Inference Telemetry Tooltip */}
      {activeNode && activeDeviceState && (
        <div className="absolute bottom-6 right-6 z-[1000] w-72 bg-white/95 dark:bg-slate-950/90 backdrop-blur-xl border border-gray-200/50 dark:border-slate-800/80 rounded-2xl p-4 shadow-2xl transition-colors duration-300 pointer-events-none">
          <div className="flex items-start justify-between mb-3 pb-2 border-b dark:border-slate-800/50">
            <div>
              <h4 className="text-gray-900 dark:text-white font-bold text-sm truncate">{activeNode.name}</h4>
              <p className="text-[10px] text-gray-400 font-mono truncate">{activeNode.id.slice(0, 8)}...</p>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
              activeNode.status === 'online'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                : 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400'
            }`}>
              {activeNode.status}
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1">Active Deployment</span>
              {activeDeployment ? (
                <div className="space-y-2">
                  <div className="font-semibold text-xs text-gray-900 dark:text-white">
                    {activeDeployment.name || `Dep ${activeDeployment.id.slice(0, 8)}`}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] bg-gray-50 dark:bg-slate-900/50 p-2 rounded-lg border border-gray-100 dark:border-slate-800/40">
                    <div>
                      <span className="text-gray-400 block uppercase font-semibold">Model</span>
                      <span className="text-gray-700 dark:text-slate-200 truncate block font-medium">{activeModel?.name || "—"}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block uppercase font-semibold">Script</span>
                      <span className="text-gray-700 dark:text-slate-200 truncate block font-medium">{activeScript?.name || "—"}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <span className="text-xs text-gray-500 dark:text-slate-400 italic">No active deployment</span>
              )}
            </div>

            {activeDeployment && (
              <div className="border-t dark:border-slate-800/50 pt-3">
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
                  Live Inference Output
                </span>
                {loadingInference ? (
                  <span className="text-xs text-gray-400 italic block">Reading predictions...</span>
                ) : inferenceResults.length === 0 ? (
                  <span className="text-xs text-gray-400 italic block">No predictions recorded</span>
                ) : (() => {
                  const result = inferenceResults[0];
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
                  
                  if (detections.length === 0) {
                    return <span className="text-xs text-gray-500 dark:text-slate-400 italic block">No targets detected</span>;
                  }

                  return (
                    <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto mt-1">
                      {detections.map((det: any, idx: number) => (
                        <div key={idx} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/40 border border-blue-100/50 dark:border-blue-900/30 text-[10px] font-bold text-blue-700 dark:text-blue-400">
                          <span>{det.class}</span>
                          {det.confidence !== undefined ? (
                            <span className="opacity-80">({Math.round(det.confidence * 100)}%)</span>
                          ) : det.value !== undefined ? (
                            <span className="opacity-80">({String(det.value)})</span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
