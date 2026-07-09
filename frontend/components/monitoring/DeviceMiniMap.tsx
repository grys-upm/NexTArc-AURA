"use client";
import dynamic from "next/dynamic";

const DynamicMiniMap = dynamic(() => import("./DeviceMiniMapInternal"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[220px] bg-slate-50 dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 flex flex-col items-center justify-center space-y-2">
      <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">Loading map...</p>
    </div>
  )
});

interface DeviceMiniMapProps {
  coordinates?: [number, number]; // [lon, lat]
  status: string;
}

export function DeviceMiniMap({ coordinates, status }: DeviceMiniMapProps) {
  if (!coordinates || coordinates.length !== 2) {
    return (
      <div className="w-full h-[220px] bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-dashed border-gray-200 dark:border-slate-800 flex flex-col items-center justify-center p-4 text-center">
        <p className="text-sm font-bold text-gray-500 dark:text-gray-400">No Location Data</p>
        <p className="text-xs text-gray-400 max-w-[200px] mt-1">This node has not reported spatial coordinates.</p>
      </div>
    );
  }

  return <DynamicMiniMap coordinates={coordinates} status={status} />;
}
