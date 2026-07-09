"use client";
import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

// Dynamically import the map to disable Server-Side Rendering
const DynamicMap = dynamic(() => import("./MapInternal"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[500px] bg-slate-900 rounded-3xl border border-slate-800 flex flex-col items-center justify-center text-slate-500">
      <Loader2 size={32} className="animate-spin mb-4 text-blue-500" />
      <p className="text-sm font-medium">Initializing Tactical Map Engine...</p>
    </div>
  ),
});

interface EdgeMapProps {
  states?: any[];
}

export function EdgeMap(props: EdgeMapProps) {
  return <DynamicMap {...props} />;
}