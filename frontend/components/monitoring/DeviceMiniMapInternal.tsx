"use client";
import React from "react";
import { MapContainer, TileLayer, Marker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useTheme } from "next-themes";

interface DeviceMiniMapInternalProps {
  coordinates: [number, number]; // [lon, lat]
  status: string;
}

const createTacticalIcon = (status: string, isDark: boolean) => {
  const shadowOpacity = isDark ? "0.5" : "0.7"; 
  
  let colorClass = `bg-blue-500 text-blue-500 shadow-[0_0_15px_rgba(59,130,246,${shadowOpacity})]`;
  if (status === "warning") colorClass = `bg-yellow-500 text-yellow-500 shadow-[0_0_15px_rgba(234,179,8,${shadowOpacity})]`;
  if (status === "offline") colorClass = `bg-red-500 text-red-500 shadow-[0_0_15px_rgba(239,68,68,${shadowOpacity})]`;

  const isOffline = status === "offline";

  const htmlString = `
    <div class="relative flex items-center justify-center w-full h-full cursor-default">
      ${!isOffline ? `
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div class="w-8 h-8 rounded-full border border-current absolute animate-ping opacity-30 ${colorClass}"></div>
        </div>
      ` : ''}
      <div class="w-3 h-3 rounded-full ${colorClass} relative z-10 border border-white/20"></div>
    </div>
  `;

  return L.divIcon({
    html: htmlString,
    className: "transparent-leaflet-icon",
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
};

export default function DeviceMiniMapInternal({ coordinates, status }: DeviceMiniMapInternalProps) {
  const { theme, systemTheme } = useTheme();
  const currentTheme = theme === "system" ? systemTheme : theme;
  const isDark = currentTheme === "dark";

  const center: [number, number] = [coordinates[1], coordinates[0]]; // [lat, lon]
  const tileUrl = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

  return (
    <div className="w-full h-[220px] rounded-2xl border border-gray-200 dark:border-slate-800 relative overflow-hidden flex flex-col z-0">
      <MapContainer 
        center={center} 
        zoom={12} 
        scrollWheelZoom={false} 
        zoomControl={false}
        className="w-full h-full !bg-transparent" 
      >
        <TileLayer
          key={isDark ? "dark" : "light"}
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
          url={tileUrl}
          className={isDark ? "dark-tactical-tiles" : ""}
        />
        <Marker 
          position={center}
          icon={createTacticalIcon(status, isDark)}
        />
      </MapContainer>
    </div>
  );
}
