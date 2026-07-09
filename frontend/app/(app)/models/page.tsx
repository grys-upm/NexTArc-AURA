"use client";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getModels, uploadModel, deleteModel,
  getDatasets, createDataset, deleteDataset,
  associateModelDataset, replaceDatasetFile,
  getModelDownloadUrl, getDatasetDownloadUrl,
  getDatasetVersionDownloadUrl,
  getBaseModelOptions, trainModel,
  getBaseModelDownloadUrl,
  Dataset, Model,
  updateModel, updateDataset
} from "@/lib/api";

import { HW_LABELS } from "@/lib/utils";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import {
  Brain, Plus, Trash2, Upload, CheckCircle, XCircle,
  Loader2, Clock, Layers, RotateCcw, Info, Database, HardDrive, Download, Tag, Terminal
} from "lucide-react";

const STATUS_CONFIG = {
  ready: { icon: CheckCircle, color: "text-emerald-500", badge: "success" as const },
  training: { icon: Loader2, color: "text-pink-500 animate-spin", badge: "warning" as const },
  compiling: { icon: Loader2, color: "text-amber-500 animate-spin", badge: "warning" as const },
  failed: { icon: XCircle, color: "text-red-500", badge: "danger" as const },
  pending: { icon: Clock, color: "text-gray-400", badge: "muted" as const },
};

const normalizeStatus = (status: string) => {
  if (status === "ready" || status === "training" || status === "failed" || status === "pending" || status === "compiling") {
    return status;
  }
  return "pending";
};

const parseModelName = (name: string) => {
  const yoloMatch = name.match(/^(yolov\d+|yolox)(.*)$/i);
  if (yoloMatch) {
    return { family: yoloMatch[1].toLowerCase(), version: yoloMatch[2] || "" };
  }
  const generalMatch = name.match(/^([a-zA-Z]+)(.*)$/);
  if (generalMatch) {
    return { family: generalMatch[1].toLowerCase(), version: generalMatch[2] || "" };
  }
  return { family: "other", version: name };
};

const formatVersionLabel = (version: string) => {
  let label = version.replace(/\.pt$/i, "");
  if (label.startsWith("_") || label.startsWith("-")) label = label.slice(1);
  return label || "standard";
};

const formatFamilyName = (family: string) => {
  if (family.startsWith("yolo")) return "YOLO" + family.slice(4);
  return family.charAt(0).toUpperCase() + family.slice(1);
};

const formatSize = (bytes: number | null | undefined) => {
  if (!bytes) return "0 Bytes";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(2)} MB`;
};

const stripAnsi = (str: string) => {
  return str
    .replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqty=><]/g, '')
    .replace(/\[\d+m/g, '');
};

export default function ModelsPage() {

  const [activeTab, setActiveTab] = useState<"models" | "baseModels">("models");
  const [selectedBaseModelVersions, setSelectedBaseModelVersions] = useState<Record<string, string>>({});

  // Local pending items
  const [pendingModels, setPendingModels] = useState<any[]>([]);
  const [pendingDatasets, setPendingDatasets] = useState<any[]>([]);

  // Edit Model Modal
  const [editModelOpen, setEditModelOpen] = useState(false);
  const [selectedModelForEdit, setSelectedModelForEdit] = useState<Model | null>(null);
  const [editModelForm, setEditModelForm] = useState({
    name: "", description: "", base_architecture: "", epochs: "", input_size: "", batch_size: ""
  });

  // Manage Dataset Modal
  const [manageDatasetOpen, setManageDatasetOpen] = useState(false);
  const [selectedDatasetForManage, setSelectedDatasetForManage] = useState<Dataset | null>(null);
  const [editDatasetForm, setEditDatasetForm] = useState({ name: "", description: "" });
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [newVersionName, setNewVersionName] = useState("");
  const [newVersionDescription, setNewVersionDescription] = useState("");
  const replaceFileRef = useRef<HTMLInputElement>(null);

  // Associate Modal
  const [associateOpen, setAssociateOpen] = useState(false);
  const [selectedModelForAssociation, setSelectedModelForAssociation] = useState<Model | null>(null);
  const [associationDatasetId, setAssociationDatasetId] = useState("");
  const [associationDatasetVersionId, setAssociationDatasetVersionId] = useState("");

  const handleDownload = async (
    e: React.MouseEvent,
    fetchUrlPromise: () => Promise<{ url: string }>
  ) => {
    try {
      const { url } = await fetchUrlPromise();
      const a = document.createElement("a");
      a.href = url; a.download = "";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
    } catch (err: any) {
      console.error("Download error:", err);
      const detail = err?.response?.data?.detail || err?.message || "Download failed";
      showTooltip(e, detail);
    }
  };

  const qc = useQueryClient();

  const { data: models = [], isLoading: isModelsLoading } = useQuery({
    queryKey: ["models"], queryFn: getModels, refetchInterval: 5000,
  });

  const { data: datasets = [], isLoading: isDatasetsLoading } = useQuery({
    queryKey: ["datasets"], queryFn: getDatasets,
  });

  const { data: baseModelOptions = [] } = useQuery({
    queryKey: ["baseModelOptions"], queryFn: getBaseModelOptions,
  });

  const sortedBaseModelOptions = [...baseModelOptions].sort((a, b) => {
    const parseNum = (name: string) => {
      const match = name.match(/yolov(\d+)/i);
      return match ? parseInt(match[1], 10) : -1;
    };
    const numA = parseNum(a); const numB = parseNum(b);
    if (numA !== numB) return numB - numA;
    return a.localeCompare(b);
  });

  const groupedBaseModels = (() => {
    const groups: Record<string, { fullName: string; label: string }[]> = {};
    baseModelOptions.forEach((modelName) => {
      const { family, version } = parseModelName(modelName);
      const label = formatVersionLabel(version);
      if (!groups[family]) groups[family] = [];
      groups[family].push({ fullName: modelName, label });
    });
    return groups;
  })();

  const baseModelFamilies = Object.keys(groupedBaseModels).sort((a, b) => {
    const matchA = a.match(/^yolov(\d+)$/i);
    const matchB = b.match(/^yolov(\d+)$/i);
    if (matchA && matchB) return parseInt(matchB[1], 10) - parseInt(matchA[1], 10);
    if (matchA) return -1; if (matchB) return 1;
    return a.localeCompare(b);
  });



  const displayedModels = [
    ...pendingModels.filter((pm: any) => !models.some((m: any) => m.name === pm.name)),
    ...models
  ];

  const mappedDatasets = datasets.map((d: any) => {
    const isPending = pendingDatasets.some((pd: any) => pd.name === d.name);
    if (isPending && !d.object_key) {
      return { ...d, status: "pending", isPendingUpload: true };
    }
    return { ...d, status: "ready" };
  });

  const displayedDatasets = [
    ...pendingDatasets.filter((pd: any) => !datasets.some((d: any) => d.name === pd.name)),
    ...mappedDatasets
  ];

  // --- UI State ---
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "", description: "", dataset_id: "", dataset_version_id: "", base_model: "", epochs: "", input_size: "", batch_size: ""
  });
  const [file, setFile] = useState<File | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // View Logs Modal
  const [viewLogsOpen, setViewLogsOpen] = useState(false);
  const [selectedModelForLogs, setSelectedModelForLogs] = useState<Model | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    const fetchLogs = async () => {
      if (!viewLogsOpen || !selectedModelForLogs) return;

      try {
        const token = localStorage.getItem("aura_token");
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/models/${selectedModelForLogs.id}/logs`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (active) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              setLogs(prev => {
                const newLogs = [...prev, data];
                if (newLogs.length > 5000) return newLogs.slice(newLogs.length - 5000);
                return newLogs;
              });
            }
          }
        }
      } catch (err) {
        console.error("Error reading log stream", err);
      }
    };

    if (viewLogsOpen) {
      setLogs([]); // clear on open
      fetchLogs();
    }
    return () => { active = false; };
  }, [viewLogsOpen, selectedModelForLogs]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // Create Dataset Modal
  const [createDatasetOpen, setCreateDatasetOpen] = useState(false);
  const [newDatasetForm, setNewDatasetForm] = useState({ name: "", description: "", version: "", version_description: "" });
  const [newDatasetFile, setNewDatasetFile] = useState<File | null>(null);
  const newDatasetFileRef = useRef<HTMLInputElement>(null);

  // Training Form
  const [trainForm, setTrainForm] = useState({
    name: "", description: "", dataset_id: "", dataset_version_id: "", base_model: "",
    epochs: "20", input_size: "640x640", gpu_percent: "0.9", device: "0"
  });
  const [trainPocError, setTrainPocError] = useState("");

  // Retraining Form & Modal State
  const [retrainOpen, setRetrainOpen] = useState(false);
  const [selectedModelForRetrain, setSelectedModelForRetrain] = useState<Model | null>(null);
  const [retrainForm, setRetrainForm] = useState({
    name: "", description: "", dataset_id: "", dataset_version_id: "",
    epochs: "20", input_size: "640x640", gpu_percent: "0.9", device: "0"
  });

  // --- Mutations ---
  const startTrainingMutation = useMutation({
    mutationFn: () => trainModel({
      name: trainForm.name,
      description: trainForm.description,
      dataset_id: trainForm.dataset_id,
      dataset_version_id: trainForm.dataset_version_id || undefined,
      base_model: trainForm.base_model,
      epochs: parseInt(trainForm.epochs) || 20,
      input_size: trainForm.input_size,
      gpu_percent: parseFloat(trainForm.gpu_percent) || 0.9,
      device: trainForm.device
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      setTrainForm({ name: "", description: "", dataset_id: "", dataset_version_id: "", base_model: "", epochs: "20", input_size: "640x640", gpu_percent: "0.9", device: "0" });
    }
  });

  const startRetrainingMutation = useMutation({
    mutationFn: () => {
      if (!selectedModelForRetrain) throw new Error("No model selected for retraining");
      return trainModel({
        name: retrainForm.name,
        description: retrainForm.description,
        dataset_id: retrainForm.dataset_id,
        dataset_version_id: retrainForm.dataset_version_id || undefined,
        base_model: selectedModelForRetrain.source_key || `${selectedModelForRetrain.id}/model.pt`,
        epochs: parseInt(retrainForm.epochs) || 20,
        input_size: retrainForm.input_size,
        gpu_percent: parseFloat(retrainForm.gpu_percent) || 0.9,
        device: retrainForm.device
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      setRetrainOpen(false);
      setSelectedModelForRetrain(null);
      setRetrainForm({ name: "", description: "", dataset_id: "", dataset_version_id: "", epochs: "20", input_size: "640x640", gpu_percent: "0.9", device: "0" });
    }
  });

  const upload = useMutation({
    onMutate: async () => {
      const tempId = `temp-model-${Date.now()}`;
      setPendingModels(prev => [...prev, {
        id: tempId, name: form.name, description: form.description,
        compile_status: "pending", base_architecture: form.base_model,
        dataset_id: form.dataset_id,
        dataset_version_id: form.dataset_version_id,
        epochs: form.epochs ? parseInt(form.epochs) : undefined,
        input_size: form.input_size,
        batch_size: form.batch_size ? parseInt(form.batch_size) : undefined,
        isPendingUpload: true,
      }]);
      return { tempId };
    },
    mutationFn: () => uploadModel(
      form.name, form.description, file!,
      form.dataset_id || undefined,
      form.base_model || undefined,
      form.epochs ? parseInt(form.epochs) : undefined,
      form.input_size || undefined,
      form.batch_size ? parseInt(form.batch_size) : undefined,
      form.dataset_version_id || undefined
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      setOpen(false); setFile(null);
      setForm({ name: "", description: "", dataset_id: "", dataset_version_id: "", base_model: "", epochs: "", input_size: "", batch_size: "" });
    },
    onSettled: (_, __, ___, context) => {
      if (context?.tempId) setPendingModels(prev => prev.filter(m => m.id !== context.tempId));
    }
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteModel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });

  const createDatasetMutation = useMutation({
    onMutate: async (variables) => {
      setCreateDatasetOpen(false);
      setNewDatasetFile(null);
      setNewDatasetForm({ name: "", description: "", version: "", version_description: "" });
      const tempId = `temp-ds-${Date.now()}`;
      setPendingDatasets(prev => [...prev, { id: tempId, name: variables.name, description: variables.description, status: "pending", isPendingUpload: true }]);
      return { tempId };
    },
    mutationFn: (body: { name: string; description: string; file?: File; version?: string; version_description?: string }) => createDataset(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (err: any, _, context) => {
      if (context?.tempId) {
        setPendingDatasets(prev => prev.map(d =>
          d.id === context.tempId
            ? { ...d, status: "failed", error: err?.response?.data?.detail || err?.message || "Failed to upload" }
            : d
        ));
      }
    },
    onSettled: (_, error, __, context) => {
      if (!error && context?.tempId) setPendingDatasets(prev => prev.filter(d => d.id !== context.tempId));
    }
  });

  const removeDatasetMutation = useMutation({
    mutationFn: (id: string) => deleteDataset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });

  const replaceFileMutation = useMutation({
    mutationFn: (args: { datasetId: string; file: File; version?: string; description?: string }) =>
      replaceDatasetFile(args.datasetId, args.file, args.version, args.description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setReplaceFile(null);
      setNewVersionName("");
      setNewVersionDescription("");
    }
  });

  const associateMutation = useMutation({
    mutationFn: (args: { modelId: string; datasetId: string; datasetVersionId?: string }) =>
      associateModelDataset(args.modelId, args.datasetId, args.datasetVersionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      setAssociateOpen(false);
      setAssociationDatasetId("");
      setAssociationDatasetVersionId("");
    },
  });

  const updateModelMutation = useMutation({
    mutationFn: (args: { id: string; body: any }) => updateModel(args.id, args.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      setEditModelOpen(false); setSelectedModelForEdit(null);
    }
  });

  const updateDatasetMutation = useMutation({
    mutationFn: (args: { id: string; body: any }) => updateDataset(args.id, args.body),
    onSuccess: (updatedDs) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setSelectedDatasetForManage(prev => prev ? { ...prev, name: updatedDs.name, description: updatedDs.description } : null);
    }
  });

  // --- Helpers ---
  const showTooltip = (e: React.MouseEvent, text: string) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltip({ x: rect.left + rect.width, y: rect.top, text });
    setTimeout(() => setTooltip(null), 2500);
  };

  const getModelDatasetLabel = (model: any) => {

    if (!model.dataset_id) return "No dataset associated";
    const ds = datasets.find((d: any) => d.id === model.dataset_id);
    if (!ds) return `Dataset: ${model.dataset_id.slice(0, 8)}...`;

    if (model.dataset_version_id && ds.versions) {
      const ver = ds.versions.find((v: any) => v.id === model.dataset_version_id);
      if (ver) {
        return `${ds.name} (${ver.version})`;
      }
    }
    return ds.name;
  };

  const isUploadDisabled = !file || !form.base_model || upload.isPending;

  const ZipHint = () => (
    <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/30 rounded-lg p-3 text-xs text-blue-700 dark:text-blue-400 space-y-1.5">
      <p className="font-semibold flex items-center gap-1">
        <Info size={14} className="text-blue-500" /> ZIP Folder Structure Required:
      </p>
      <pre className="font-mono text-[10px] leading-relaxed bg-white dark:bg-gray-900/80 p-2 rounded border border-blue-50 dark:border-blue-950/30">
        {`<data_dir>/\n├── images/\n│   ├── img1.jpg\n│   └── ...\n├── labels/\n│   ├── img1.txt\n│   └── ...\n└── classes.json          # {"index": "class_name", ...}`}
      </pre>
    </div>
  );

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">

      {tooltip && (
        <div
          className="fixed z-[100] bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl"
          style={{ top: `${tooltip.y}px`, left: `${tooltip.x + 10}px` }}
        >
          {tooltip.text}
          <div className="absolute left-[-6px] top-2 w-3 h-3 bg-gray-900 rotate-45" />
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500 mb-2 pb-1">
            Models &amp; Training
          </h1>
          <p className="text-gray-600 dark:text-gray-400">Manage AI models and training datasets.</p>
        </div>
        <Button onClick={() => setOpen(true)} className="gap-2 shrink-0">
          <Plus size={16} /> Upload model
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 gap-2 overflow-x-auto pb-px">
        <button
          onClick={() => setActiveTab("models")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${activeTab === "models"
            ? "border-pink-500 text-pink-600 dark:text-pink-400 font-bold"
            : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
        >
          <Brain size={16} /> Trained &amp; Uploaded Models
        </button>
        <button
          onClick={() => setActiveTab("baseModels")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${activeTab === "baseModels"
            ? "border-pink-500 text-pink-600 dark:text-pink-400 font-bold"
            : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
        >
          <Layers size={16} /> Base Models (MinIO)
        </button>
      </div>

      {activeTab === "models" ? (
        <div className="grid gap-4">
          {isModelsLoading ? (
            <div className="text-center py-10 text-gray-500">Loading models...</div>
          ) : displayedModels.length === 0 ? (
            <Card className="border-dashed border-2 bg-transparent shadow-none opacity-60">
              <div className="flex items-center justify-between p-4">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center border border-gray-200 dark:border-gray-700">
                    <Brain size={20} className="text-gray-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base font-bold text-gray-500 dark:text-gray-400">Empty Model Slot</span>
                      <Badge variant="muted">N/A</Badge>
                    </div>
                    <p className="text-xs text-gray-400">No models uploaded yet</p>
                  </div>
                </div>
                <Button variant="outline" size="sm" className="gap-2 shrink-0" onClick={() => setOpen(true)}>
                  <Upload size={14} /> Upload First Model
                </Button>
              </div>
            </Card>
          ) : (
            displayedModels.map((m: any) => {
              const normalizedStatus = normalizeStatus(m.compile_status);
              const cfg = STATUS_CONFIG[normalizedStatus];
              const StatusIcon = cfg.icon;
              return (
                <Card key={m.id} className="group hover:border-pink-500 transition-colors">
                  <div className="flex items-center justify-between p-4">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-xl bg-gray-50 dark:bg-gray-800 flex items-center justify-center border border-gray-100 dark:border-gray-700 animate-fade-in">
                        <StatusIcon size={20} className={cfg.color} />
                      </div>
                      <div>
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className="text-base font-bold text-gray-900 dark:text-white mr-1">{m.name}</span>
                          <Badge variant={cfg.badge}>{normalizedStatus}</Badge>
                          {m.compilations && m.compilations.length > 0 ? (
                            m.compilations.map((c: any) => {
                              const cStatus = normalizeStatus(c.compile_status);
                              if (cStatus === "compiling") {
                                return (
                                  <Badge key={c.id} variant="warning" className="bg-amber-50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-900/30 animate-pulse" title={c.compile_error || undefined}>
                                    Compiling: {HW_LABELS[c.hardware_type] || c.hardware_type}
                                  </Badge>
                                );
                              } else if (cStatus === "failed") {
                                return (
                                  <Badge key={c.id} variant="danger" className="bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 border-red-100 dark:border-red-900/30 font-semibold" title={c.compile_error || undefined}>
                                    Compile Failed: {HW_LABELS[c.hardware_type] || c.hardware_type}
                                  </Badge>
                                );
                              } else if (cStatus === "ready") {
                                return (
                                  <Badge key={c.id} variant="success" className="bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-900/30">
                                    Compiled: {HW_LABELS[c.hardware_type] || c.hardware_type}
                                  </Badge>
                                );
                              }
                              return null;
                            })
                          ) : m.hardware_type ? (
                            normalizedStatus === "compiling" ? (
                              <Badge variant="warning" className="bg-amber-50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-900/30 animate-pulse">
                                Compiling: {HW_LABELS[m.hardware_type] || m.hardware_type}
                              </Badge>
                            ) : normalizedStatus === "failed" ? (
                              <Badge variant="danger" className="bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 border-red-100 dark:border-red-900/30">
                                Compile Failed: {HW_LABELS[m.hardware_type] || m.hardware_type}
                              </Badge>
                            ) : (
                              <Badge variant="success" className="bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-900/30">
                                Compiled: {HW_LABELS[m.hardware_type] || m.hardware_type}
                              </Badge>
                            )
                          ) : (
                            normalizedStatus === "ready" && (
                              <Badge variant="muted" className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-100 dark:border-gray-700">
                                Uncompiled (Source)
                              </Badge>
                            )
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500 mt-1">
                          {(m.base_architecture || m.base_model) && (
                            <div className="flex items-center gap-1.5" title="Base Model">
                              <Layers size={13} className="text-gray-400" />
                              <span className="font-mono text-gray-600 dark:text-gray-300">{m.base_architecture || m.base_model}</span>
                            </div>
                          )}
                          <div className="flex items-center gap-1.5" title="Dataset">
                            <Database size={13} className="text-gray-400" />
                            <span>{getModelDatasetLabel(m)}</span>
                          </div>
                        </div>
                        {(m.epochs || m.input_size || m.batch_size) && (
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs mt-3">
                            {m.epochs ? (
                              <Badge variant="muted" className="bg-purple-50/50 dark:bg-purple-950/20 text-purple-600 dark:text-purple-400 border-purple-100 dark:border-purple-900/30">
                                Epochs: {m.epochs}
                              </Badge>
                            ) : null}
                            {m.input_size && (
                              <Badge variant="muted" className="bg-amber-50/50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-900/30">
                                Size: {m.input_size}
                              </Badge>
                            )}
                            {m.batch_size ? (
                              <Badge variant="muted" className="bg-teal-50/50 dark:bg-teal-950/20 text-teal-600 dark:text-teal-400 border-teal-100 dark:border-teal-900/30">
                                Batch: {m.batch_size}
                              </Badge>
                            ) : null}
                          </div>
                        )}
                        {m.compilations && m.compilations.some((c: any) => c.compile_status === "failed" && c.compile_error) ? (
                          m.compilations.filter((c: any) => c.compile_status === "failed" && c.compile_error).map((c: any) => (
                            <p key={c.id} className="text-xs text-red-500 mt-2 font-mono bg-red-50 dark:bg-red-950/20 p-2 rounded border border-red-100 dark:border-red-900/30 max-w-xl animate-fade-in">
                              <span className="font-bold">{HW_LABELS[c.hardware_type] || c.hardware_type} error: </span>
                              {c.compile_error}
                            </p>
                          ))
                        ) : m.compile_error ? (
                          <p className="text-xs text-red-500 mt-2 font-mono bg-red-50 dark:bg-red-950/20 p-2 rounded border border-red-100 dark:border-red-900/30 max-w-xl animate-fade-in">
                            {m.compile_error}
                          </p>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline" size="sm" className="gap-2 shrink-0 border-gray-200 dark:border-gray-700"
                        onClick={() => {
                          setSelectedModelForAssociation(m);
                          setAssociationDatasetId(m.dataset_id || "");
                          setAssociationDatasetVersionId(m.dataset_version_id || "");
                          setAssociateOpen(true);
                        }}
                        disabled={m.isPendingUpload}
                      >
                        <Database size={14} /> Dataset
                      </Button>
                      <Button
                        variant="outline" size="sm" className="gap-2 shrink-0 border-gray-200 dark:border-gray-700"
                        onClick={e => handleDownload(e, () => getModelDownloadUrl(m.id, "source"))}
                        disabled={m.isPendingUpload}
                      >
                        <Download size={14} /> Download
                      </Button>
                      <Button
                        variant="outline" size="sm" className="gap-2 shrink-0 border-gray-200 dark:border-gray-700"
                        onClick={() => {
                          setSelectedModelForEdit(m);
                          setEditModelForm({
                            name: m.name, description: m.description || "",
                            base_architecture: m.base_architecture || m.base_model || "",
                            epochs: m.epochs ? String(m.epochs) : "",
                            input_size: m.input_size || "",
                            batch_size: m.batch_size ? String(m.batch_size) : ""
                          });
                          setEditModelOpen(true);
                        }}
                        disabled={m.isPendingUpload}
                      >
                        Manage
                      </Button>
                      {(m.compile_status === "training" || m.compile_status === "compiling" || m.compile_status === "failed") && (
                        <Button
                          variant="outline" size="sm" className="gap-2 shrink-0 border-gray-200 dark:border-gray-700 text-pink-600 hover:text-pink-700 hover:bg-pink-50"
                          onClick={() => {
                            setSelectedModelForLogs(m);
                            setViewLogsOpen(true);
                          }}
                        >
                          <Terminal size={14} /> View Logs
                        </Button>
                      )}
                      <Button
                        variant="ghost" size="sm" className="gap-2 shrink-0 text-pink-600 hover:text-pink-700 dark:text-pink-400 dark:hover:text-pink-300"
                        onClick={() => {
                          setSelectedModelForRetrain(m);
                          setRetrainForm({
                            name: `${m.name}-retrained`,
                            description: m.description || "",
                            dataset_id: m.dataset_id || "",
                            dataset_version_id: m.dataset_version_id || "",
                            epochs: m.epochs ? String(m.epochs) : "20",
                            input_size: m.input_size || "640x640",
                            gpu_percent: "0.9",
                            device: "0"
                          });
                          setRetrainOpen(true);
                        }}
                        disabled={m.isPendingUpload}
                      >
                        <RotateCcw size={14} /> Retrain
                      </Button>
                      <button
                        onClick={() => remove.mutate(m.id)}
                        className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        disabled={m.isPendingUpload}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {baseModelOptions.length === 0 ? (
            <div className="col-span-full text-center py-10 text-gray-500">
              No base models found in MinIO.
            </div>
          ) : (
            baseModelFamilies.map((family) => {
              const variants = groupedBaseModels[family];
              const selectedValue = selectedBaseModelVersions[family] || (variants[0] ? variants[0].fullName : "");
              return (
                <Card key={family} className="group hover:border-pink-500 transition-colors">
                  <div className="flex flex-col gap-4 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-xl bg-pink-50 dark:bg-pink-950/20 flex items-center justify-center border border-pink-100 dark:border-pink-900/30 shrink-0">
                          <Layers size={20} className="text-pink-500" />
                        </div>
                        <div>
                          <h3 className="text-base font-bold text-gray-900 dark:text-white">
                            {formatFamilyName(family)}
                          </h3>
                          <span className="text-xs text-gray-400 font-mono block mt-0.5 break-all">
                            {selectedValue || "No versions"}
                          </span>
                        </div>
                      </div>
                      <Badge variant="success" className="shrink-0">Stored in MinIO</Badge>
                    </div>
                    <div className="pt-2 flex items-end gap-2">
                      {variants.length > 1 ? (
                        <div className="flex-1">
                          <Select
                            label="Select Version"
                            value={selectedValue}
                            onChange={(e) => setSelectedBaseModelVersions((prev) => ({ ...prev, [family]: e.target.value }))}
                            options={variants.map((v) => ({ value: v.fullName, label: v.label }))}
                          />
                        </div>
                      ) : (
                        <div className="flex-1 text-xs text-gray-500 flex items-center gap-1.5 h-9">
                          <Badge variant="muted">Ready for Training</Badge>
                        </div>
                      )}
                      <Button
                        variant="outline" size="sm"
                        className="h-9 w-9 p-0 flex items-center justify-center border-gray-200 dark:border-gray-700 shrink-0"
                        onClick={(e) => handleDownload(e, () => getBaseModelDownloadUrl(selectedValue))}
                        title="Download Base Model" disabled={!selectedValue}
                      >
                        <Download size={14} />
                      </Button>
                    </div>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      )}

      {/* Training + Dataset section */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-8 border-t border-gray-200 dark:border-gray-800">

        <div id="new-training-job-card">
          <Card className="border-pink-200 dark:border-pink-900/30 p-6">
            <CardTitle className="mb-4 flex items-center gap-2">
              <Brain className="text-pink-500" size={20} /> New Training Job
            </CardTitle>
            <form
              onSubmit={e => {
                e.preventDefault();
                setTrainPocError("");
                startTrainingMutation.mutate();
              }}
              className="space-y-4"
            >
              <Input
                label="Model Name"
                value={trainForm.name}
                onChange={e => setTrainForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. door-detector-trained"
                required
              />
              <Select
                label="Select Dataset"
                value={trainForm.dataset_id}
                onChange={e => setTrainForm(f => ({ ...f, dataset_id: e.target.value, dataset_version_id: "" }))}
                options={[
                  { value: "", label: "Select Dataset..." },
                  ...displayedDatasets.filter((d: any) => d.object_key).map((d: any) => ({ value: d.id, label: d.name }))
                ]}
                required
              />
              {trainForm.dataset_id && (() => {
                const selectedDs = displayedDatasets.find((d: any) => d.id === trainForm.dataset_id);
                if (selectedDs && selectedDs.versions && selectedDs.versions.length > 0) {
                  return (
                    <Select
                      label="Dataset Version"
                      value={trainForm.dataset_version_id}
                      onChange={e => setTrainForm(f => ({ ...f, dataset_version_id: e.target.value }))}
                      options={[
                        { value: "", label: "Latest Version (Default)" },
                        ...selectedDs.versions.map((v: any) => ({ value: v.id, label: `${v.version} - ${v.description || 'No description'}` }))
                      ]}
                    />
                  );
                }
                return null;
              })()}
              <Select
                label="Base Model"
                value={trainForm.base_model}
                onChange={e => setTrainForm(f => ({ ...f, base_model: e.target.value }))}
                options={[
                  { value: "", label: "Select Base Model" },
                  ...sortedBaseModelOptions.map(opt => ({ value: opt, label: opt }))
                ]}
                required
              />
              <div className="grid grid-cols-2 gap-4">
                <Input label="Epochs" type="number" min={1} value={trainForm.epochs}
                  onChange={e => setTrainForm(f => ({ ...f, epochs: e.target.value }))} required />
                <Input label="Image Size" value={trainForm.input_size}
                  onChange={e => setTrainForm(f => ({ ...f, input_size: e.target.value }))}
                  placeholder="e.g. 640x640" required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Input label="GPU RAM Fraction" type="number" step="0.05" min="0.1" max="1.0"
                  value={trainForm.gpu_percent}
                  onChange={e => setTrainForm(f => ({ ...f, gpu_percent: e.target.value }))} required />
                <Select label="Training Device" value={trainForm.device}
                  onChange={e => setTrainForm(f => ({ ...f, device: e.target.value }))}
                  options={[{ value: "0", label: "NVIDIA GPU 0" }, { value: "cpu", label: "CPU" }]}
                  required />
              </div>
              {trainPocError && (
                <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
                  {trainPocError}
                </div>
              )}
              {startTrainingMutation.isError && (
                <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
                  {(startTrainingMutation.error as any)?.response?.data?.detail || (startTrainingMutation.error as any)?.message || "Failed to start training"}
                </div>
              )}
              <Button
                type="submit"
                className="w-full bg-pink-600 hover:bg-pink-700"
                disabled={!trainForm.name.trim() || !trainForm.dataset_id || !trainForm.base_model || startTrainingMutation.isPending}
                loading={startTrainingMutation.isPending}
              >
                Start Training
              </Button>
            </form>
          </Card>
        </div>

        <Card className="border-emerald-200 dark:border-emerald-900/30 p-6">
          <CardTitle className="mb-4 flex items-center gap-2">
            <Layers className="text-emerald-500" size={20} /> Dataset Management
          </CardTitle>
          {isDatasetsLoading ? (
            <div className="text-center py-6 text-gray-500">Loading datasets...</div>
          ) : displayedDatasets.length === 0 ? (
            <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 text-center text-sm text-gray-500 italic">
              No datasets uploaded yet.
            </div>
          ) : (
            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
              {displayedDatasets.map((ds: any) => (
                <div key={ds.id} className="flex flex-col gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700">
                  <div className="flex items-center justify-between w-full">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold">{ds.name}</span>
                        {ds.isPendingUpload || ds.status === "pending" ? (
                          <Badge variant="warning">pending</Badge>
                        ) : ds.object_key ? (
                          <Badge variant="success">ready</Badge>
                        ) : (
                          <Badge variant="muted">no file</Badge>
                        )}
                        {ds.status === "failed" && <Badge variant="danger">failed</Badge>}
                      </div>
                      <span className="text-xs text-gray-400 truncate max-w-[200px]">{ds.description || "No description"}</span>
                      {ds.object_key && (
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                          {ds.metadata?.num_classes !== undefined && (
                            <span className="flex items-center gap-1"><Tag size={9} /> {ds.metadata.num_classes} classes</span>
                          )}
                          {ds.size_bytes && (
                            <span className="flex items-center gap-1"><HardDrive size={9} /> {formatSize(ds.size_bytes)}</span>
                          )}
                        </div>
                      )}
                      {ds.error && (
                        <span className="text-[10px] text-red-500 font-mono mt-1 block max-w-[250px] break-words">{ds.error}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      {ds.status === "failed" ? (
                        <button
                          onClick={() => setPendingDatasets(prev => prev.filter(d => d.id !== ds.id))}
                          className="p-1.5 text-gray-400 hover:text-red-500 transition-colors" title="Dismiss"
                        >
                          <Trash2 size={14} />
                        </button>
                      ) : (
                        <>
                          {ds.object_key && (
                            <Button
                              variant="ghost" size="sm"
                              onClick={(e) => handleDownload(e, () => getDatasetDownloadUrl(ds.id))}
                              title="Download Dataset" className="p-1.5 text-gray-500 hover:text-emerald-500"
                              disabled={ds.isPendingUpload}
                            >
                              <Download size={14} />
                            </Button>
                          )}
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => {
                              setSelectedDatasetForManage(ds);
                              setEditDatasetForm({ name: ds.name, description: ds.description || "" });
                              setNewVersionName("");
                              setNewVersionDescription("");
                              setManageDatasetOpen(true);
                            }}
                            disabled={ds.isPendingUpload}
                          >
                            Manage
                          </Button>
                            <button
                              onClick={() => removeDatasetMutation.mutate(ds.id)}
                              className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                              title="Delete Dataset" disabled={ds.isPendingUpload}
                            >
                              <Trash2 size={14} />
                            </button>
                        </>
                      )}
                    </div>
                  </div>
                  {/* Versions history log */}
                  {ds.versions && ds.versions.length > 0 && (
                    <div className="mt-2 pl-2 border-l-2 border-pink-500/40 space-y-1.5 max-h-[120px] overflow-y-auto">
                      <span className="text-[10px] font-bold text-gray-400 block">VERSION HISTORY:</span>
                      {ds.versions.map((v: any) => (
                        <div key={v.id} className="flex items-center justify-between text-[10px] bg-white dark:bg-gray-950 px-2 py-1 rounded border border-gray-100 dark:border-gray-800 hover:border-pink-300 dark:hover:border-pink-900 transition-colors">
                          <div className="flex items-center gap-1.5 truncate">
                            <Badge variant="muted" className="py-0.5 text-[8px] bg-pink-50 dark:bg-pink-950/20 text-pink-600 dark:text-pink-400 font-normal">
                              {v.version}
                            </Badge>
                            <span className="text-gray-500 truncate" title={v.description}>{v.description || "No description"}</span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0 ml-2 text-gray-400 font-mono">
                            <span>{v.metadata?.num_classes !== undefined ? `${v.metadata.num_classes} cls` : ""}</span>
                            <span>{formatSize(v.size_bytes)}</span>
                            <button
                              type="button"
                              onClick={(e) => handleDownload(e, () => getDatasetVersionDownloadUrl(ds.id, v.id))}
                              className="text-gray-400 hover:text-emerald-500 p-0.5 transition-colors"
                              title="Download Version ZIP"
                            >
                              <Download size={10} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <Button
            variant="outline" className="w-full mt-4"
            onClick={() => setCreateDatasetOpen(true)}
          >
            <Upload size={16} className="mr-2" /> Create Dataset
          </Button>
        </Card>

      </section>

      {/* Upload model modal */}
      <Modal open={open} onClose={() => { setOpen(false); setFile(null); }} title="Upload Model">
        <form onSubmit={e => { e.preventDefault(); if (file) upload.mutate(); }} className="flex flex-col gap-5 pt-4">
          <Input label="Model name" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. yolov8n-door-detector" required />
          <Input label="Description (optional)" value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Brief description..." />
            <Select
              label="Dataset (optional)"
              value={form.dataset_id}
              onChange={e => setForm(f => ({ ...f, dataset_id: e.target.value, dataset_version_id: "" }))}
              options={[
                { value: "", label: "Select Dataset (optional)" },
                ...datasets.map((d: any) => ({ value: d.id, label: d.name }))
              ]}
            />
            {form.dataset_id && (() => {
              const selectedDs = datasets.find((d: any) => d.id === form.dataset_id);
              if (selectedDs && selectedDs.versions && selectedDs.versions.length > 0) {
                return (
                  <Select
                    label="Dataset Version (optional)"
                    value={form.dataset_version_id}
                    onChange={e => setForm(f => ({ ...f, dataset_version_id: e.target.value }))}
                    options={[
                      { value: "", label: "Latest Version (Default)" },
                      ...selectedDs.versions.map((v: any) => ({ value: v.id, label: `${v.version} - ${v.description || 'No description'}` }))
                    ]}
                  />
                );
              }
              return null;
            })()}
          <div className="border-t border-gray-150 dark:border-gray-800 pt-4 space-y-4">
            <h4 className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
              Model Configuration &amp; Metadata
            </h4>
            <Select
              label="Base Model" value={form.base_model}
              onChange={e => setForm(f => ({ ...f, base_model: e.target.value }))}
              options={[
                { value: "", label: "Select Base Model" },
                ...sortedBaseModelOptions.map(opt => ({ value: opt, label: opt }))
              ]} required />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Input label="Epochs" type="number" min={1} value={form.epochs}
                onChange={e => setForm(f => ({ ...f, epochs: e.target.value }))} placeholder="e.g. 100" />
              <Input label="Input Size" value={form.input_size}
                onChange={e => setForm(f => ({ ...f, input_size: e.target.value }))} placeholder="e.g. 640x640" />
              <Input label="Batch Size" type="number" min={1} value={form.batch_size}
                onChange={e => setForm(f => ({ ...f, batch_size: e.target.value }))} placeholder="e.g. 16" />
            </div>
          </div>
          <div
            className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl p-8 flex flex-col items-center cursor-pointer hover:border-pink-400 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload size={28} className="text-gray-400 mb-2" />
            <p className="text-sm text-gray-500">
              {file ? <span className="text-pink-500 font-medium">{file.name}</span> : "Click to upload .pt file"}
            </p>
            <input ref={fileRef} type="file" accept=".pt" className="hidden"
              onChange={e => setFile(e.target.files?.[0] || null)} />
          </div>
          {upload.isError && (
            <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
              Failed to upload: {(upload.error as any)?.response?.data?.detail || upload.error?.message || "An error occurred"}
            </div>
          )}
          <Button type="submit" className="w-full" disabled={isUploadDisabled} loading={upload.isPending}>
            Upload Model
          </Button>
        </form>
      </Modal>

      {/* Create Dataset Modal */}
      <Modal
        open={createDatasetOpen}
        onClose={() => { setCreateDatasetOpen(false); setNewDatasetFile(null); setNewDatasetForm({ name: "", description: "", version: "", version_description: "" }); }}
        title="Create Dataset"
      >
        <form
          onSubmit={e => {
            e.preventDefault();
            if (newDatasetForm.name.trim()) {
              createDatasetMutation.mutate({
                name: newDatasetForm.name,
                description: newDatasetForm.description,
                file: newDatasetFile || undefined,
                version: newDatasetForm.version || undefined,
                version_description: newDatasetForm.version_description || undefined,
              });
            }
          }}
          className="flex flex-col gap-5 pt-4"
        >
          <Input label="Dataset Name" value={newDatasetForm.name}
            onChange={e => setNewDatasetForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. Traffic Sign Detection" required />
          <Input label="Description (optional)" value={newDatasetForm.description}
            onChange={e => setNewDatasetForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Describe the classes, source, etc." />

          <div className="border-t border-gray-200 dark:border-gray-800 pt-4 flex flex-col gap-4">
            <h4 className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
              Dataset File &amp; Version (optional)
            </h4>
            <ZipHint />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Initial Version Name"
                value={newDatasetForm.version}
                onChange={e => setNewDatasetForm(f => ({ ...f, version: e.target.value }))}
                placeholder="e.g. v1 (auto-generated if empty)"
              />
              <Input
                label="Version Description"
                value={newDatasetForm.version_description}
                onChange={e => setNewDatasetForm(f => ({ ...f, version_description: e.target.value }))}
                placeholder="e.g. Initial capture"
              />
            </div>
            <div
              className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-6 flex flex-col items-center cursor-pointer hover:border-pink-400 transition-colors"
              onClick={() => newDatasetFileRef.current?.click()}
            >
              <Upload size={20} className="text-gray-400 mb-1" />
              <p className="text-xs text-gray-500 text-center">
                {newDatasetFile
                  ? <span className="text-pink-500 font-medium">{newDatasetFile.name}</span>
                  : "Click to upload dataset ZIP file"}
              </p>
              <input ref={newDatasetFileRef} type="file" accept=".zip" className="hidden"
                onChange={e => setNewDatasetFile(e.target.files?.[0] || null)} />
            </div>
          </div>

          <Button type="submit" className="w-full mt-2"
            disabled={!newDatasetForm.name.trim() || createDatasetMutation.isPending}
            loading={createDatasetMutation.isPending}>
            Create Dataset
          </Button>
        </form>
      </Modal>

      {/* Manage Dataset Modal */}
      <Modal
        open={manageDatasetOpen}
        onClose={() => { setManageDatasetOpen(false); setSelectedDatasetForManage(null); setReplaceFile(null); }}
        title={`Manage Dataset: ${selectedDatasetForManage?.name || ""}`}
      >
        <div className="flex flex-col gap-6 pt-4 px-1">
          {/* Dataset Details */}
          {selectedDatasetForManage && (
            <form
              onSubmit={e => {
                e.preventDefault();
                if (editDatasetForm.name.trim()) {
                  updateDatasetMutation.mutate({
                    id: selectedDatasetForManage.id,
                    body: { name: editDatasetForm.name, description: editDatasetForm.description }
                  });
                }
              }}
              className="flex flex-col gap-4 border-b border-gray-200 dark:border-gray-800 pb-6"
            >
              <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">Dataset Details</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Dataset Name" value={editDatasetForm.name}
                  onChange={e => setEditDatasetForm(f => ({ ...f, name: e.target.value }))} required />
                <Input label="Description" value={editDatasetForm.description}
                  onChange={e => setEditDatasetForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div className="flex justify-end">
                <Button type="submit" size="sm" loading={updateDatasetMutation.isPending}>Save Changes</Button>
              </div>
            </form>
          )}

          {/* Current File Info */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">Current File</h3>
            {selectedDatasetForManage?.object_key ? (
              <div className="p-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-gray-950 dark:text-gray-50">Dataset ZIP</span>
                    <Badge variant="success">uploaded</Badge>
                  </div>
                  <Button
                    variant="ghost" size="sm" className="h-6 w-6 p-0 text-gray-400 hover:text-emerald-500"
                    onClick={e => handleDownload(e, () => getDatasetDownloadUrl(selectedDatasetForManage.id))}
                    title="Download ZIP"
                  >
                    <Download size={14} />
                  </Button>
                </div>
                <div className="flex items-center gap-4 text-[10px] text-gray-400 border-t border-gray-100 dark:border-gray-800 pt-1.5">
                  <span className="font-mono">SHA: {selectedDatasetForManage.sha256?.slice(0, 12)}...</span>
                  {selectedDatasetForManage.metadata?.num_classes !== undefined && (
                    <span className="flex items-center gap-1"><Tag size={9} /> {selectedDatasetForManage.metadata.num_classes} classes</span>
                  )}
                  {selectedDatasetForManage.size_bytes && (
                    <span className="flex items-center gap-1"><HardDrive size={9} /> {formatSize(selectedDatasetForManage.size_bytes)}</span>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic">No file uploaded yet.</p>
            )}
          </div>

          {/* Replace/Upload File */}
          <form
            onSubmit={e => {
              e.preventDefault();
              if (selectedDatasetForManage && replaceFile) {
                replaceFileMutation.mutate({
                  datasetId: selectedDatasetForManage.id,
                  file: replaceFile,
                  version: newVersionName,
                  description: newVersionDescription,
                });
              }
            }}
            className="border-t border-gray-200 dark:border-gray-800 pt-4 flex flex-col gap-4"
          >
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
              {selectedDatasetForManage?.object_key ? "Upload New Dataset Version" : "Upload Dataset File (v1)"}
            </h3>
            <ZipHint />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Version Name (optional)"
                value={newVersionName}
                onChange={e => setNewVersionName(e.target.value)}
                placeholder="e.g. v2, v1.1.0 (auto-generated if empty)"
              />
              <Input
                label="Version Description (optional)"
                value={newVersionDescription}
                onChange={e => setNewVersionDescription(e.target.value)}
                placeholder="e.g. Added winter classes"
              />
            </div>
            <div
              className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-6 flex flex-col items-center cursor-pointer hover:border-pink-400 transition-colors"
              onClick={() => replaceFileRef.current?.click()}
            >
              <Upload size={20} className="text-gray-400 mb-1" />
              <p className="text-xs text-gray-500 text-center">
                {replaceFile
                  ? <span className="text-pink-500 font-medium">{replaceFile.name}</span>
                  : "Click to upload dataset ZIP file"}
              </p>
              <input ref={replaceFileRef} type="file" accept=".zip" className="hidden"
                onChange={e => setReplaceFile(e.target.files?.[0] || null)} required />
            </div>
            {replaceFileMutation.isError && (
              <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
                {(replaceFileMutation.error as any)?.response?.data?.detail || (replaceFileMutation.error as any)?.message || "An error occurred"}
              </div>
            )}
            <Button
              type="submit" className="w-full"
              disabled={!replaceFile || replaceFileMutation.isPending}
              loading={replaceFileMutation.isPending}
            >
              Upload New Version
            </Button>
          </form>
        </div>
      </Modal>

      {/* Associate Dataset Modal */}
      <Modal
        open={associateOpen}
        onClose={() => { setAssociateOpen(false); setSelectedModelForAssociation(null); setAssociationDatasetId(""); setAssociationDatasetVersionId(""); }}
        title={`Associate Dataset: ${selectedModelForAssociation?.name || ""}`}
      >
        <form
          onSubmit={e => {
            e.preventDefault();
            if (selectedModelForAssociation && associationDatasetId) {
              associateMutation.mutate({
                modelId: selectedModelForAssociation.id,
                datasetId: associationDatasetId,
                datasetVersionId: associationDatasetVersionId || undefined
              });
            }
          }}
          className="flex flex-col gap-4 pt-4"
        >
          <Select
            label="Dataset"
            value={associationDatasetId}
            onChange={e => {
              setAssociationDatasetId(e.target.value);
              setAssociationDatasetVersionId("");
            }}
            options={[
              { value: "", label: "Select Dataset..." },
              ...datasets.map((d: any) => ({ value: d.id, label: d.name }))
            ]}
            required
          />
          {associationDatasetId && (() => {
            const selectedDs = datasets.find((d: any) => d.id === associationDatasetId);
            if (selectedDs && selectedDs.versions && selectedDs.versions.length > 0) {
              return (
                <Select
                  label="Dataset Version"
                  value={associationDatasetVersionId}
                  onChange={e => setAssociationDatasetVersionId(e.target.value)}
                  options={[
                    { value: "", label: "Latest Version (Default)" },
                    ...selectedDs.versions.map((v: any) => ({ value: v.id, label: `${v.version} - ${v.description || 'No description'}` }))
                  ]}
                />
              );
            }
            return null;
          })()}
          {associateMutation.isError && (
            <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
              Failed to associate: {(associateMutation.error as any)?.response?.data?.detail || (associateMutation.error as any)?.message || "An error occurred"}
            </div>
          )}
          <Button
            type="submit" className="w-full mt-2"
            disabled={!associationDatasetId || associateMutation.isPending}
            loading={associateMutation.isPending}
          >
            Save Association
          </Button>
        </form>
      </Modal>

      {/* Edit Model Modal */}
      <Modal
        open={editModelOpen}
        onClose={() => { setEditModelOpen(false); setSelectedModelForEdit(null); }}
        title={`Edit Model: ${selectedModelForEdit?.name || ""}`}
      >
        <form
          onSubmit={e => {
            e.preventDefault();
            if (selectedModelForEdit && editModelForm.name.trim()) {
              updateModelMutation.mutate({
                id: selectedModelForEdit.id,
                body: {
                  name: editModelForm.name, description: editModelForm.description,
                  epochs: editModelForm.epochs ? parseInt(editModelForm.epochs) : undefined,
                  input_size: editModelForm.input_size || undefined,
                  batch_size: editModelForm.batch_size ? parseInt(editModelForm.batch_size) : undefined,
                  base_architecture: editModelForm.base_architecture || undefined
                }
              });
            }
          }}
          className="flex flex-col gap-5 pt-4"
        >
          <Input label="Model Name" value={editModelForm.name}
            onChange={e => setEditModelForm(f => ({ ...f, name: e.target.value }))} required />
          <Input label="Description (optional)" value={editModelForm.description}
            onChange={e => setEditModelForm(f => ({ ...f, description: e.target.value }))} />
          <Select
            label="Base Model" value={editModelForm.base_architecture}
            onChange={e => setEditModelForm(f => ({ ...f, base_architecture: e.target.value }))}
            options={[
              { value: "", label: "Select Base Model" },
              ...sortedBaseModelOptions.map(opt => ({ value: opt, label: opt }))
            ]}
          />
          <div className="grid grid-cols-3 gap-4">
            <Input label="Epochs" type="number" min={1} value={editModelForm.epochs}
              onChange={e => setEditModelForm(f => ({ ...f, epochs: e.target.value }))} />
            <Input label="Input Size" value={editModelForm.input_size}
              onChange={e => setEditModelForm(f => ({ ...f, input_size: e.target.value }))} placeholder="e.g. 640x640" />
            <Input label="Batch Size" type="number" min={1} value={editModelForm.batch_size}
              onChange={e => setEditModelForm(f => ({ ...f, batch_size: e.target.value }))} />
          </div>
          {updateModelMutation.isError && (
            <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
              Failed to save: {(updateModelMutation.error as any)?.response?.data?.detail || updateModelMutation.error?.message || "An error occurred"}
            </div>
          )}
          <Button type="submit" className="w-full mt-2"
            disabled={!editModelForm.name.trim() || updateModelMutation.isPending}
            loading={updateModelMutation.isPending}>
            Save Changes
          </Button>
        </form>
      </Modal>

      {/* Retrain Model Modal */}
      <Modal
        open={retrainOpen}
        onClose={() => { setRetrainOpen(false); setSelectedModelForRetrain(null); }}
        title={`Retrain Model: ${selectedModelForRetrain?.name || ""}`}
      >
        <form
          onSubmit={e => {
            e.preventDefault();
            if (selectedModelForRetrain && retrainForm.name.trim() && retrainForm.dataset_id) {
              startRetrainingMutation.mutate();
            }
          }}
          className="flex flex-col gap-5 pt-4"
        >
          <Input 
            label="Model Name" 
            value={retrainForm.name}
            onChange={e => setRetrainForm(f => ({ ...f, name: e.target.value }))} 
            required 
          />
          <Input 
            label="Description (optional)" 
            value={retrainForm.description}
            onChange={e => setRetrainForm(f => ({ ...f, description: e.target.value }))} 
          />
          <Select
            label="Select Dataset"
            value={retrainForm.dataset_id}
            onChange={e => setRetrainForm(f => ({ ...f, dataset_id: e.target.value, dataset_version_id: "" }))}
            options={[
              { value: "", label: "Select Dataset..." },
              ...displayedDatasets.filter((d: any) => d.object_key).map((d: any) => ({ value: d.id, label: d.name }))
            ]}
            required
          />
          {retrainForm.dataset_id && (() => {
            const selectedDs = displayedDatasets.find((d: any) => d.id === retrainForm.dataset_id);
            if (selectedDs && selectedDs.versions && selectedDs.versions.length > 0) {
              return (
                <Select
                  label="Dataset Version"
                  value={retrainForm.dataset_version_id}
                  onChange={e => setRetrainForm(f => ({ ...f, dataset_version_id: e.target.value }))}
                  options={[
                    { value: "", label: "Latest Version (Default)" },
                    ...selectedDs.versions.map((v: any) => ({ value: v.id, label: `${v.version} - ${v.description || 'No description'}` }))
                  ]}
                />
              );
            }
            return null;
          })()}
          <div className="grid grid-cols-2 gap-4">
            <Input 
              label="Epochs" 
              type="number" 
              min={1} 
              value={retrainForm.epochs}
              onChange={e => setRetrainForm(f => ({ ...f, epochs: e.target.value }))} 
              required 
            />
            <Input 
              label="Image Size" 
              value={retrainForm.input_size}
              onChange={e => setRetrainForm(f => ({ ...f, input_size: e.target.value }))} 
              placeholder="e.g. 640x640" 
              required 
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input 
              label="GPU RAM Fraction" 
              type="number" 
              step="0.05" 
              min="0.1" 
              max="1.0"
              value={retrainForm.gpu_percent}
              onChange={e => setRetrainForm(f => ({ ...f, gpu_percent: e.target.value }))} 
              required 
            />
            <Select 
              label="Training Device" 
              value={retrainForm.device}
              onChange={e => setRetrainForm(f => ({ ...f, device: e.target.value }))}
              options={[{ value: "0", label: "NVIDIA GPU 0" }, { value: "cpu", label: "CPU" }]}
              required 
            />
          </div>
          {startRetrainingMutation.isError && (
            <div className="p-3 text-sm bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 text-red-600 dark:text-red-400 rounded-lg animate-fade-in">
              Failed to start retraining: {(startRetrainingMutation.error as any)?.response?.data?.detail || startRetrainingMutation.error?.message || "An error occurred"}
            </div>
          )}
          <Button 
            type="submit" 
            className="w-full mt-2 bg-pink-600 hover:bg-pink-700 text-white font-medium shadow-md shadow-pink-500/10 hover:shadow-pink-500/20 transition-all duration-200"
            disabled={!retrainForm.name.trim() || !retrainForm.dataset_id || startRetrainingMutation.isPending}
            loading={startRetrainingMutation.isPending}
          >
            Start Retraining
          </Button>
        </form>
      </Modal>

      {/* View Logs Modal */}
      <Modal
        open={viewLogsOpen}
        onClose={() => { setViewLogsOpen(false); setSelectedModelForLogs(null); }}
        title={`Training Logs: ${selectedModelForLogs?.name || ""}`}
        size="xl"
      >
        <div className="pt-4">
          <div className="bg-gray-950 rounded-lg p-4 font-mono text-xs text-gray-300 h-[70vh] overflow-y-auto whitespace-pre-wrap flex flex-col gap-1 border border-gray-800 shadow-inner">
            {logs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-3">
                <Loader2 className="animate-spin" size={24} />
                <p>Waiting for logs stream...</p>
              </div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className={`${log.toLowerCase().includes('error') ? 'text-red-400' : log.toLowerCase().includes('warning') ? 'text-yellow-400' : ''}`}>
                  {stripAnsi(log)}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </Modal>
    </div>
  );
}