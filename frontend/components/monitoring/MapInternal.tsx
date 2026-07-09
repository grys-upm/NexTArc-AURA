"use client";
import React, { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useTheme } from "next-themes";
import { useQuery } from "@tanstack/react-query";
import { getDevices } from "@/lib/api";
import { MapPin, Server, Activity, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";

interface EdgeMapProps {
  states?: any[];
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

export default function MapInternal({ states = [] }: EdgeMapProps) {
  const { theme, systemTheme } = useTheme();
  const [activeNode, setActiveNode] = useState<any | null>(null);
  const [markers, setMarkers] = useState<any[]>([]);
  const router = useRouter();

  const { data: devices = [] } = useQuery({
    queryKey: ["devices"],
    queryFn: getDevices,
  });

  const currentTheme = theme === "system" ? systemTheme : theme;
  const isDark = currentTheme === "dark";

  // IMPORTANT: We now ALWAYS use the clean detailed map.
  // The dark magic will be handled by CSS.
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
          cpu: s.cpu_percent,
          ram: s.ram_percent,
          latency: s.latency_ms
        };
      });
    setMarkers(realMarkers);
  }, [states, devices]);

  if (markers.length === 0) {
    return (
      <div className="w-full h-[500px] bg-gray-50 dark:bg-slate-900 rounded-3xl border border-gray-200 dark:border-slate-800 p-8 relative overflow-hidden flex items-center justify-center">
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

  return (
    <div className="w-full h-[500px] bg-gray-100 dark:bg-slate-900 rounded-3xl border border-gray-200 dark:border-slate-800 relative overflow-hidden flex flex-col z-0">
      
      <div className="absolute top-6 left-6 z-[1000] pointer-events-none">
        <h3 className="text-gray-900 dark:text-white font-bold text-lg flex items-center gap-2">
          <MapPin size={18} className="text-blue-500"/>
          Tactical Edge Overview
        </h3>
        <p className="text-gray-500 dark:text-slate-400 text-xs mt-1">Live high-resolution telemetry mapping</p>
      </div>

      <MapContainer 
        center={defaultCenter} 
        zoom={13} 
        scrollWheelZoom={true} 
        className="w-full h-full !bg-transparent" 
        zoomControl={false}
      >
        <TileLayer
          key={isDark ? "dark" : "light"} // Forces redraw when changing themes
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
          url={tileUrl}
          className={isDark ? "dark-tactical-tiles" : ""} // <--- Apply the magic filter here
        />

        {markers.map((marker) => (
          <Marker 
            key={marker.id} 
            position={marker.coordinates as [number, number]}
            icon={createTacticalIcon(marker.status, isDark)}
            eventHandlers={{
              mouseover: () => setActiveNode(marker),
              mouseout: () => setActiveNode(null),
              click: () => router.push(`/devices/${marker.id}?from=monitoring`),
            }}
          />
        ))}
      </MapContainer>

      {/* Floating Telemetry Tooltip */}
      {activeNode && (
        <div className="absolute bottom-6 right-6 z-[1000] w-64 bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl border border-gray-200 dark:border-slate-700 rounded-xl p-4 shadow-2xl pointer-events-none transition-colors">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h4 className="text-gray-900 dark:text-white font-bold text-sm truncate">{activeNode.name}</h4>
              <p className="text-xs text-gray-500 dark:text-slate-400 font-mono">{activeNode.id}</p>
            </div>
            {activeNode.status === 'online' && <Activity size={16} className="text-blue-500 dark:text-blue-400" />}
            {activeNode.status === 'warning' && <AlertTriangle size={16} className="text-yellow-500 dark:text-yellow-400" />}
            {activeNode.status === 'offline' && <Server size={16} className="text-red-500 dark:text-red-400" />}
          </div>
          
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500 dark:text-slate-400">CPU Load</span>
                <span className={activeNode.cpu > 80 ? "text-yellow-600 dark:text-yellow-400 font-bold" : "text-gray-900 dark:text-white"}>{activeNode.cpu}%</span>
              </div>
              <div className="w-full h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full ${activeNode.cpu > 80 ? 'bg-yellow-400' : 'bg-blue-500'}`} style={{ width: `${activeNode.cpu}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500 dark:text-slate-400">RAM Usage</span>
                <span className="text-gray-900 dark:text-white">{activeNode.ram}%</span>
              </div>
              <div className="w-full h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500" style={{ width: `${activeNode.ram}%` }} />
              </div>
            </div>
            {typeof activeNode.latency === "number" && activeNode.latency >= 0 && (
              <div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500 dark:text-slate-400">Latency</span>
                  <span className="text-gray-955 dark:text-white font-bold font-mono">{activeNode.latency.toFixed(5)} ms</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}