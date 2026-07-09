"use client";
import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

const DynamicMap = dynamic(() => import("./DeploymentMapInternal"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-slate-900 rounded-3xl border border-slate-800 flex flex-col items-center justify-center text-slate-500">
      <Loader2 size={32} className="animate-spin mb-4 text-blue-500" />
      <p className="text-sm font-medium">Initializing Deployment Map Engine...</p>
    </div>
  ),
});

interface DeploymentMapProps {
  states?: any[];
  deployments?: any[];
  devices?: any[];
  models?: any[];
  scripts?: any[];
}

export function DeploymentMap(props: DeploymentMapProps) {
  return <DynamicMap {...props} />;
}
