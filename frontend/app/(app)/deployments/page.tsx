"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDeployments, getDevices, getModels, getScripts, createDeployment, deleteDeployment, getMonitoringStates } from "@/lib/api";
import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import { Modal } from "@/components/ui/Modal";
import { HW_LABELS, fmtRelative } from "@/lib/utils";
import { Rocket, Plus, Check, AlertTriangle, Trash2, Edit, RotateCcw } from "lucide-react";
import { DeploymentMap } from "@/components/monitoring/DeploymentMap";

const STATUS_VARIANT: Record<string, any> = {
  running: "success",
  sent: "info",
  pending: "secondary",
  compiling: "warning",
  failed: "destructive",
  stopped: "destructive",
};

export default function DeploymentsPage() {
  const qc = useQueryClient();
  const { data: deployments = [], isLoading } = useQuery({ queryKey: ["deployments"], queryFn: getDeployments, refetchInterval: 5000 });
  const { data: devices = [] } = useQuery({ queryKey: ["devices"], queryFn: getDevices });
  const { data: models = [] } = useQuery({ queryKey: ["models"], queryFn: getModels });
  const { data: scripts = [] } = useQuery({ queryKey: ["scripts"], queryFn: getScripts });
  const { data: states = [] } = useQuery({ queryKey: ["monitoring"], queryFn: getMonitoringStates, refetchInterval: 5000 });

  const [open, setOpen] = useState(false);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>([]);
  const [modelId, setModelId] = useState("");
  const [scriptId, setScriptId] = useState("");
  const [name, setName] = useState("");
  const [deployErr, setDeployErr] = useState("");
  const [deployingCount, setDeployingCount] = useState(0);
  const [repeatingId, setRepeatingId] = useState<string | null>(null);

  const readyModels = models.filter((m: any) => m.compile_status === "ready");

  const handleEdit = (d: any) => {
    setSelectedDeviceIds([d.device_id]);
    setModelId(d.model_id);
    setScriptId(d.script_id);
    setName(d.name || "");
    setOpen(true);
  };

  // Backend accepts one deployment at a time (device_id singular)
  // We create one per selected device sequentially
  const deployMutation = useMutation({
    mutationFn: (device_id: string) =>
      createDeployment({ device_ids: [device_id], model_id: modelId, script_id: scriptId, name }),
    onError: (e: any) => setDeployErr(e?.response?.data?.detail || "Deployment failed"),
  });

  const cancelDeploymentMutation = useMutation({
    mutationFn: (id: string) => deleteDeployment(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deployments"] }),
  });

  const repeatMutation = useMutation({
    mutationFn: (d: any) =>
      createDeployment({
        device_ids: [d.device_id],
        model_id: d.model_id,
        script_id: d.script_id,
        name: d.name || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployments"] });
    },
  });

  const handleRepeat = async (d: any) => {
    setRepeatingId(d.id);
    setDeployErr("");
    try {
      await repeatMutation.mutateAsync(d);
    } catch (err: any) {
      setDeployErr(err?.response?.data?.detail || "Failed to repeat deployment");
    } finally {
      setRepeatingId(null);
    }
  };

  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedDeviceIds.length === 0) return;
    setDeployErr("");
    setDeployingCount(selectedDeviceIds.length);
    for (const device_id of selectedDeviceIds) {
      await deployMutation.mutateAsync(device_id).catch(() => { });
    }
    qc.invalidateQueries({ queryKey: ["deployments"] });
    setOpen(false);
    setSelectedDeviceIds([]);
    setModelId("");
    setScriptId("");
    setName("");
    setDeployingCount(0);
  };

  const toggleDevice = (id: string) => {
    setSelectedDeviceIds(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    );
  };

  const getDeviceName = (id: string) => devices.find((d: any) => d.id === id)?.name || id.slice(0, 8);
  const getModelName = (id: string) => models.find((m: any) => m.id === id)?.name || id.slice(0, 8);
  const getScriptName = (id: string) => scripts.find((s: any) => s.id === id)?.name || id.slice(0, 8);

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500 mb-2 pb-1">
            Deployments
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Manage device model updates and rollouts.
          </p>
        </div>
        <Button onClick={() => setOpen(true)} className="gap-2 shrink-0">
          <Plus size={16} /> New Deployment
        </Button>
      </div>

      {deployErr && !open && (
        <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-xl flex items-center justify-between gap-3 text-sm text-red-650 dark:text-red-400">
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-red-500 shrink-0" />
            <span>{deployErr}</span>
          </div>
          <button type="button" onClick={() => setDeployErr("")} className="text-xs font-semibold text-gray-450 hover:text-gray-700 dark:hover:text-gray-250 transition-colors underline">
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch min-h-[750px]">
        {/* Left Column: Map */}
        <div className="lg:col-span-7 flex flex-col relative w-full h-full">
          <DeploymentMap
            states={states}
            deployments={deployments}
            devices={devices}
            models={models}
            scripts={scripts}

          />
        </div>

        {/* Right Column: Deployments list */}
        <div className="lg:col-span-5 space-y-4 overflow-y-auto pr-1">
          {isLoading ? (
            <div className="text-center py-10 text-gray-500">Loading deployments...</div>
          ) : deployments.length === 0 ? (
            <Card className="border-dashed border-2 bg-transparent shadow-none opacity-60 h-full flex flex-col justify-center">
              <div className="flex flex-col items-center justify-center p-6 text-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center border border-gray-200 dark:border-gray-700">
                  <Rocket size={20} className="text-gray-400" />
                </div>
                <div>
                  <div className="flex items-center justify-center gap-2 mb-1">
                    <span className="text-base font-bold text-gray-500 dark:text-gray-400">Empty Deployment Slot</span>
                    <Badge variant="muted">N/A</Badge>
                  </div>
                  <p className="text-xs text-gray-400">No active deployments</p>
                </div>
                <Button variant="outline" size="sm" className="gap-2 w-full" onClick={() => setOpen(true)}>
                  <Plus size={14} /> Create First Deployment
                </Button>
              </div>
            </Card>
          ) : (
            deployments.map((d: any) => (
              <Card key={d.id} className={`hover:border-blue-400 transition-all ${d.status === "failed" ? "border-red-300 dark:border-red-900/50" : ""}`}>
                <div className="flex items-center justify-between p-1">
                  <div className="flex items-center gap-3 min-w-0">
                    <StatusDot status={d.status} />
                    <div className="min-w-0">
                      <p className="font-bold text-gray-900 dark:text-white truncate">
                        {d.name || `Deployment ${d.id.slice(0, 8)}`}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5 truncate">
                        <Link href={`/devices/${d.device_id}`} className="font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-350 hover:underline transition-colors">
                          {getDeviceName(d.device_id)}
                        </Link>
                        {" · "}
                        <span className="font-mono text-gray-400">{d.id.slice(0, 8)}</span>
                      </p>
                      <p className="text-[10px] text-gray-400 mt-0.5 truncate">
                        <span>{getModelName(d.model_id)}</span>
                        {" · "}
                        <span>{getScriptName(d.script_id)}</span>
                      </p>
                      {d.error_msg && (
                        <div className="flex items-start gap-1.5 mt-2 p-2 bg-red-50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/30 rounded-lg max-w-full" title={d.error_msg}>
                          <AlertTriangle size={13} className="text-red-500 shrink-0 mt-0.5" />
                          <p className="text-[10px] text-red-600 dark:text-red-400 font-mono break-all line-clamp-2">{d.error_msg}</p>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="flex flex-col items-end gap-1">
                      <Badge variant={STATUS_VARIANT[d.status] || "default"}>{d.status}</Badge>
                      <span className="text-[9px] text-gray-400">{fmtRelative(d.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button
                        onClick={() => handleRepeat(d)}
                        disabled={repeatingId !== null}
                        className="p-1.5 text-gray-400 hover:text-emerald-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Repeat Deployment"
                      >
                        <RotateCcw size={14} className={repeatingId === d.id ? "animate-spin" : ""} />
                      </button>
                      <button
                        onClick={() => handleEdit(d)}
                        className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors"
                        title="Modify / Edit Deployment"
                      >
                        <Edit size={14} />
                      </button>
                      <button
                        onClick={() => cancelDeploymentMutation.mutate(d.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                        title="Delete Deployment"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      </div>

      <Modal open={open} onClose={() => { setOpen(false); setDeployErr(""); setName(""); }} title="New Deployment" size="lg">
        <form onSubmit={handleDeploy} className="flex flex-col gap-6 pt-4">
          <Input
            label="Deployment Name"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Temperature Monitoring v1"
          />
          {deployErr && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-600 dark:text-red-400">
              {deployErr}
            </div>
          )}

          <div className="space-y-3">
            <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">
              Target Devices ({selectedDeviceIds.length} selected)
            </label>
            <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto p-2 border rounded-lg dark:border-gray-700">
              {devices.length === 0 ? (
                <p className="text-sm text-gray-500 italic col-span-2">No registered devices found.</p>
              ) : (
                devices.map((d: any) => (
                  <button
                    key={d.id} type="button" onClick={() => toggleDevice(d.id)}
                    className={`flex items-center gap-2 p-2 rounded-md text-sm border text-left ${selectedDeviceIds.includes(d.id)
                      ? "bg-blue-50 border-blue-500 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                      : "bg-gray-50 border-transparent dark:bg-gray-800"
                      }`}
                  >
                    {selectedDeviceIds.includes(d.id) && <Check size={14} />}
                    <div>
                      <p className="font-medium">{d.name}</p>
                      <p className="text-[10px] text-gray-400">{HW_LABELS[d.hardware_type] || d.hardware_type}</p>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Model"
              value={modelId}
              onChange={e => setModelId(e.target.value)}
              options={[
                { value: "", label: readyModels.length === 0 ? "No compiled models" : "Select model…" },
                ...readyModels.map((m: any) => ({ value: m.id, label: m.name })),
              ]}
              required
            />
            <Select
              label="Inference script"
              value={scriptId}
              onChange={e => setScriptId(e.target.value)}
              options={[
                { value: "", label: scripts.length === 0 ? "No scripts available" : "Select script…" },
                ...scripts.map((s: any) => ({ value: s.id, label: s.name })),
              ]}
              required
            />
          </div>

          <Button
            type="submit"
            className="w-full"
            disabled={selectedDeviceIds.length === 0 || !modelId || !scriptId || deployMutation.isPending}
            loading={deployMutation.isPending}
          >
            {deployMutation.isPending
              ? `Deploying... (${deployingCount} left)`
              : `Deploy to ${selectedDeviceIds.length} device${selectedDeviceIds.length !== 1 ? "s" : ""}`}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
