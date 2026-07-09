"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDevices, createDevice, deleteDevice, getHardwareTypes, getSensors, getActuators, getOthers, getPeripheralLabels, updateDevice, getInferenceResults } from "@/lib/api";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { HW_LABELS } from "@/lib/utils";
import Link from "next/link";
import {
  Cpu, Plus, Trash2, Zap, Radio, Layers, Server, Check, Info, ChevronDown, ChevronRight,
  Camera, Thermometer, Ruler, Compass, Power, Disc, Volume2, Lightbulb, Edit2, Activity, Play, MapPin
} from "lucide-react";

type TabType = "devices" | "architectures" | "sensors" | "actuators" | "nodes";

const CATEGORY_ICONS: Record<string, any> = {
  camera: Camera,
  temperature: Thermometer,
  distance: Ruler,
  imu: Compass,
  relay: Power,
  servo: Disc,
  buzzer: Volume2,
  led: Lightbulb,
  template: Server,
  gps: MapPin,
};

const getPeripheralIcon = (name: string, defaultIcon: any) => {
  const parts = name.split("/");
  const category = parts.length > 1 ? parts[0] : "";
  return CATEGORY_ICONS[category] || defaultIcon;
};

export default function DevicesPage() {
  const qc = useQueryClient();


  const { data: hardwareTypes = [] } = useQuery({
    queryKey: ["hardwareTypes"],
    queryFn: getHardwareTypes,
  });

  const { data: sensors = [] } = useQuery({
    queryKey: ["sensors"],
    queryFn: getSensors,
  });

  const { data: actuators = [] } = useQuery({
    queryKey: ["actuators"],
    queryFn: getActuators,
  });

  const { data: others = [] } = useQuery({
    queryKey: ["others"],
    queryFn: getOthers,
  });

  const { data: peripheralLabels = {} } = useQuery({
    queryKey: ["peripheralLabels"],
    queryFn: getPeripheralLabels,
    staleTime: 60_000, // labels change rarely
  });

  // Merge dynamic labels from backend (Python LABEL attrs) with static HW_LABELS fallback
  const resolveLabel = (key: string): string =>
    peripheralLabels[key] ?? HW_LABELS[key] ?? key;

  const hwOptions = hardwareTypes.map(v => ({ value: v, label: resolveLabel(v) }));

  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({
    camera: true,
    temperature: true,
    distance: true,
    imu: true,
    relay: true,
    servo: true,
    buzzer: true,
    led: true,
    template: true,
  });

  const toggleCategory = (cat: string) => {
    setExpandedCategories(prev => ({ ...prev, [cat]: !prev[cat] }));
  };

  const [activeTab, setActiveTab] = useState<TabType>("devices");
  const [openRegisterDevice, setOpenRegisterDevice] = useState(false);
  const [openRegisterComponent, setOpenRegisterComponent] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<any>(null);
  const [componentName, setComponentName] = useState("");
  const [editingModalName, setEditingModalName] = useState("");
  const [modalTab, setModalTab] = useState<"specs" | "inference">("specs");

  useEffect(() => {
    if (selectedDevice) {
      setEditingModalName(selectedDevice.name);
      setModalTab("specs");
    } else {
      setEditingModalName("");
    }
  }, [selectedDevice]);

  const updateDeviceMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateDevice(id, { name }),
    onSuccess: (updatedDevice) => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      setSelectedDevice((prev: any) => prev ? { ...prev, name: updatedDevice.name } : null);
    },
  });

  const [deviceForm, setDeviceForm] = useState({
    name: "",
    hardware_type: "hailo8",
    description: "",
    selected_sensors: [] as string[],
    selected_actuators: [] as string[],
    selected_nodes: [] as string[],
  });

  const { data: devices = [], isLoading } = useQuery({
    queryKey: ["devices"],
    queryFn: getDevices,
    refetchInterval: 5000,
  });

  const { data: inferenceResults = [], isLoading: loadingInference } = useQuery({
    queryKey: ["device-inference", selectedDevice?.id],
    queryFn: () => getInferenceResults(selectedDevice.id),
    enabled: !!selectedDevice && modalTab === "inference",
    refetchInterval: modalTab === "inference" ? 2000 : false,
  });

  const globalArchitectures = hardwareTypes;
  const globalSensors = sensors;
  const globalActuators = actuators;
  const globalNodes = others;

  const groupedSensors = globalSensors.reduce((acc, sensor) => {
    const parts = sensor.split("/");
    const category = parts.length > 1 ? parts[0] : "other";
    if (!acc[category]) acc[category] = [];
    acc[category].push(sensor);
    return acc;
  }, {} as Record<string, string[]>);

  const groupedActuators = globalActuators.reduce((acc, actuator) => {
    const parts = actuator.split("/");
    const category = parts.length > 1 ? parts[0] : "other";
    if (!acc[category]) acc[category] = [];
    acc[category].push(actuator);
    return acc;
  }, {} as Record<string, string[]>);

  const groupedNodes = globalNodes.reduce((acc, node) => {
    const parts = node.split("/");
    const category = parts.length > 1 ? parts[0] : "other";
    if (!acc[category]) acc[category] = [];
    acc[category].push(node);
    return acc;
  }, {} as Record<string, string[]>);

  const registerDevice = useMutation({
    mutationFn: () =>
      createDevice({
        name: deviceForm.name,
        hardware_type: deviceForm.hardware_type,
        description: deviceForm.description || undefined,
        sensors: deviceForm.selected_sensors,
        actuators: deviceForm.selected_actuators,
        others: deviceForm.selected_nodes,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      setOpenRegisterDevice(false);
      setDeviceForm({ name: "", hardware_type: "hailo8", description: "", selected_sensors: [], selected_actuators: [], selected_nodes: [] });
    },
  });

  const removeDevice = useMutation({
    mutationFn: (id: string) => deleteDevice(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });

  const toggleFormArray = (
    field: "selected_sensors" | "selected_actuators" | "selected_nodes",
    value: string
  ) => {
    setDeviceForm(prev => ({
      ...prev,
      [field]: prev[field].includes(value)
        ? prev[field].filter(item => item !== value)
        : [...prev[field], value],
    }));
  };

  const PoCNotice = ({ feature }: { feature: string }) => (
    <div className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-xl">
      <Info size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-amber-800 dark:text-amber-400">Not Available in this PoC</p>
        <p className="text-xs text-amber-700 dark:text-amber-500 mt-0.5">
          {feature} management is planned for a future iteration.
        </p>
      </div>
    </div>
  );

  const EmptySlotCard = ({
    icon: Icon, title, description, actionLabel, onAction,
  }: { icon: any; title: string; description: string; actionLabel?: string; onAction?: () => void }) => (
    <Card className="border-dashed border-2 bg-transparent shadow-none opacity-70 py-8">
      <div className="flex flex-col items-center text-center max-w-sm mx-auto space-y-3">
        <div className="w-12 h-12 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center border border-gray-200 dark:border-gray-700">
          <Icon size={24} className="text-gray-400" />
        </div>
        <div>
          <h3 className="text-base font-bold text-gray-700 dark:text-gray-300">{title}</h3>
          <p className="text-xs text-gray-400 mt-1">{description}</p>
        </div>
        {actionLabel && onAction && (
          <Button variant="outline" size="sm" onClick={onAction} className="gap-2">
            <Plus size={14} /> {actionLabel}
          </Button>
        )}
      </div>
    </Card>
  );

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500 mb-2 pb-1">
            Infrastructure Manager
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Orchestrate your edge gateways, structural nodes, and modular peripheral devices.
          </p>
        </div>
        {activeTab === "devices" ? (
          <Button onClick={() => setOpenRegisterDevice(true)} className="gap-2 shrink-0">
            <Plus size={16} /> Register Device
          </Button>
        ) : null}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 gap-2 overflow-x-auto pb-px">
        {([
          { id: "devices", label: "IoT Edge Devices", icon: Cpu },
          { id: "architectures", label: "Hardware Architectures", icon: Layers },
          { id: "sensors", label: "Sensors Catalog", icon: Radio },
          { id: "actuators", label: "Actuators Catalog", icon: Zap },
          { id: "nodes", label: "Others Catalog", icon: Server },
        ] as const).map(tab => {
          const TabIcon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${isActive
                ? "border-blue-500 text-blue-600 dark:text-blue-400 font-bold"
                : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
            >
              <TabIcon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* TAB: DEVICES */}
      {activeTab === "devices" && (
        <div className="space-y-4">
          {isLoading ? (
            <div className="text-center py-10 text-gray-500">Loading devices...</div>
          ) : devices.length === 0 ? (
            <EmptySlotCard
              icon={Cpu}
              title="Empty Device Topology"
              description="No edge gateways are registered yet."
              actionLabel="Register First Gateway"
              onAction={() => setOpenRegisterDevice(true)}
            />
          ) : (
            <div className="grid gap-4">
              {devices.map((d: any) => (
                <Card key={d.id} className="p-5 flex items-center justify-between hover:border-blue-500 transition-all">
                  <Link href={`/devices/${d.id}?from=devices`} className="flex items-center gap-4 flex-1 group">
                    <div className="p-3 bg-blue-50 dark:bg-gray-800 rounded-xl group-hover:scale-105 transition-all">
                      <Cpu size={22} className="text-blue-500" />
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-900 dark:text-white text-lg group-hover:text-blue-500 transition-colors">{d.name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="default">{resolveLabel(d.hardware_type)}</Badge>
                        <span className="text-xs text-gray-400 font-mono">{d.id}</span>
                      </div>
                    </div>
                  </Link>
                  <div className="flex items-center gap-3">
                    <Link href={`/devices/${d.id}?from=devices`}>
                      <Button variant="ghost" size="sm">
                        See more
                      </Button>
                    </Link>
                    <button
                      onClick={() => removeDevice.mutate(d.id)}
                      className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB: ARCHITECTURES */}
      {activeTab === "architectures" && (
        <div className="space-y-4">
          {globalArchitectures.length === 0 ? (
            <EmptySlotCard
              icon={Layers}
              title="No Base Architectures"
              description="No compiler architectures detected from the platform."
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {globalArchitectures.map((arch: string) => (
                <Card key={arch} className="p-5 border-l-4 border-l-blue-500 flex items-center justify-between">
                  <span className="font-bold text-gray-800 dark:text-gray-200">{resolveLabel(arch)}</span>
                  <Badge variant="default">Hardware Base</Badge>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB: SENSORS */}
      {activeTab === "sensors" && (
        <div className="space-y-6">
          {Object.keys(groupedSensors).length === 0 ? (
            <EmptySlotCard
              icon={Radio}
              title="No Registered Sensors"
              description="No sensor libraries detected in the platform folders."
            />
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedSensors).map(([category, items]) => {
                const isExpanded = expandedCategories[category] !== false;
                const CatIcon = CATEGORY_ICONS[category] || Radio;
                return (
                  <Card key={category} className="p-0 overflow-hidden border border-gray-200 dark:border-gray-800 shadow-sm">
                    <button
                      type="button"
                      onClick={() => toggleCategory(category)}
                      className="w-full flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900 font-bold text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <CatIcon size={16} className="text-emerald-500" />
                        {resolveLabel(category)}
                      </span>
                      {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </button>
                    {isExpanded && (
                      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 border-t dark:border-gray-800 bg-white dark:bg-gray-950">
                        {items.map((sensor: string) => (
                          <Card key={sensor} className="p-4 flex items-center justify-between border hover:border-emerald-500 transition-all bg-white dark:bg-gray-950">
                            <span className="font-semibold text-gray-850 dark:text-gray-150 flex items-center gap-2">
                              <CatIcon size={14} className="text-emerald-500/80" />
                              {resolveLabel(sensor)}
                            </span>
                            <Badge variant="success">Input Peripheral</Badge>
                          </Card>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB: ACTUATORS */}
      {activeTab === "actuators" && (
        <div className="space-y-6">
          {Object.keys(groupedActuators).length === 0 ? (
            <EmptySlotCard
              icon={Zap}
              title="No Registered Actuators"
              description="No actuator libraries detected in the platform folders."
            />
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedActuators).map(([category, items]) => {
                const isExpanded = expandedCategories[category] !== false;
                const CatIcon = CATEGORY_ICONS[category] || Zap;
                return (
                  <Card key={category} className="p-0 overflow-hidden border border-gray-200 dark:border-gray-800 shadow-sm">
                    <button
                      type="button"
                      onClick={() => toggleCategory(category)}
                      className="w-full flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900 font-bold text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <CatIcon size={16} className="text-yellow-500" />
                        {resolveLabel(category)}
                      </span>
                      {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </button>
                    {isExpanded && (
                      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 border-t dark:border-gray-800 bg-white dark:bg-gray-950">
                        {items.map((actuator: string) => (
                          <Card key={actuator} className="p-4 flex items-center justify-between border hover:border-yellow-500 transition-all bg-white dark:bg-gray-950">
                            <span className="font-semibold text-gray-850 dark:text-gray-150 flex items-center gap-2">
                              <CatIcon size={14} className="text-yellow-500/80" />
                              {resolveLabel(actuator)}
                            </span>
                            <Badge variant="warning">Output Relay</Badge>
                          </Card>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB: NODES */}
      {activeTab === "nodes" && (
        <div className="space-y-6">
          {Object.keys(groupedNodes).length === 0 ? (
            <EmptySlotCard
              icon={Server}
              title="No Registered Other Components"
              description="No other component libraries detected in the platform folders."
            />
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedNodes).map(([category, items]) => {
                const isExpanded = expandedCategories[category] !== false;
                const CatIcon = CATEGORY_ICONS[category] || Server;
                return (
                  <Card key={category} className="p-0 overflow-hidden border border-gray-200 dark:border-gray-800 shadow-sm">
                    <button
                      type="button"
                      onClick={() => toggleCategory(category)}
                      className="w-full flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900 font-bold text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <CatIcon size={16} className="text-blue-500" />
                        {resolveLabel(category)}
                      </span>
                      {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </button>
                    {isExpanded && (
                      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 border-t dark:border-gray-800 bg-white dark:bg-gray-950">
                        {items.map((node: string) => (
                          <Card key={node} className="p-4 flex items-center justify-between border hover:border-blue-500 transition-all bg-white dark:bg-gray-950">
                            <span className="font-semibold text-gray-850 dark:text-gray-150 flex items-center gap-2">
                              <CatIcon size={14} className="text-blue-500/80" />
                              {resolveLabel(node)}
                            </span>
                            <Badge variant="default">Other Device</Badge>
                          </Card>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* MODAL: DEVICE REGISTRATION */}
      <Modal open={openRegisterDevice} onClose={() => setOpenRegisterDevice(false)} title="Register New Device" size="lg">
        <form
          onSubmit={e => { e.preventDefault(); registerDevice.mutate(); }}
          className="space-y-6 pt-4"
        >
          <Input
            label="Device Label / Hostname"
            value={deviceForm.name}
            onChange={e => setDeviceForm(prev => ({ ...prev, name: e.target.value }))}
            placeholder="e.g. Edge-Gateway-01"
            required
          />

          <Select
            label="Hardware Type"
            value={deviceForm.hardware_type}
            onChange={e => setDeviceForm(prev => ({ ...prev, hardware_type: e.target.value }))}
            options={hwOptions}
          />

          <Input
            label="Description"
            value={deviceForm.description}
            onChange={e => setDeviceForm(prev => ({ ...prev, description: e.target.value }))}
            placeholder="A brief description of this device..."
          />



          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 border-t pt-4 dark:border-gray-800">
            {/* Sensors */}
            <div className="space-y-4">
              <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider block">Attached Sensors</label>
              <div className="space-y-3">
                {Object.keys(groupedSensors).length === 0 ? (
                  <p className="text-xs text-gray-400 italic">No sensors registered</p>
                ) : (
                  Object.entries(groupedSensors).map(([category, items]) => {
                    const selectedValue = items.find(v => deviceForm.selected_sensors.includes(v)) || "";
                    const options = [
                      { value: "", label: `Select ${resolveLabel(category)}...` },
                      ...items.map(v => ({ value: v, label: resolveLabel(v) }))
                    ];
                    return (
                      <div key={category} className="space-y-1">
                        <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{resolveLabel(category)}</span>
                        <Select
                          value={selectedValue}
                          onChange={e => {
                            const val = e.target.value;
                            const filtered = deviceForm.selected_sensors.filter(v => !items.includes(v));
                            const newSelection = val ? [...filtered, val] : filtered;
                            setDeviceForm(prev => ({ ...prev, selected_sensors: newSelection }));
                          }}
                          options={options}
                        />
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Actuators */}
            <div className="space-y-4">
              <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider block">Attached Actuators</label>
              <div className="space-y-3">
                {Object.keys(groupedActuators).length === 0 ? (
                  <p className="text-xs text-gray-400 italic">No actuators registered</p>
                ) : (
                  Object.entries(groupedActuators).map(([category, items]) => {
                    const selectedValue = items.find(v => deviceForm.selected_actuators.includes(v)) || "";
                    const options = [
                      { value: "", label: `Select ${resolveLabel(category)}...` },
                      ...items.map(v => ({ value: v, label: resolveLabel(v) }))
                    ];
                    return (
                      <div key={category} className="space-y-1">
                        <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{resolveLabel(category)}</span>
                        <Select
                          value={selectedValue}
                          onChange={e => {
                            const val = e.target.value;
                            const filtered = deviceForm.selected_actuators.filter(v => !items.includes(v));
                            const newSelection = val ? [...filtered, val] : filtered;
                            setDeviceForm(prev => ({ ...prev, selected_actuators: newSelection }));
                          }}
                          options={options}
                        />
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Others */}
            <div className="space-y-4">
              <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider block">Other Components</label>
              <div className="space-y-3">
                {Object.keys(groupedNodes).length === 0 ? (
                  <p className="text-xs text-gray-400 italic">No other components registered</p>
                ) : (
                  Object.entries(groupedNodes).map(([category, items]) => {
                    const selectedValue = items.find(v => deviceForm.selected_nodes.includes(v)) || "";
                    const options = [
                      { value: "", label: `Select ${resolveLabel(category)}...` },
                      ...items.map(v => ({ value: v, label: resolveLabel(v) }))
                    ];
                    return (
                      <div key={category} className="space-y-1">
                        <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{resolveLabel(category)}</span>
                        <Select
                          value={selectedValue}
                          onChange={e => {
                            const val = e.target.value;
                            const filtered = deviceForm.selected_nodes.filter(v => !items.includes(v));
                            const newSelection = val ? [...filtered, val] : filtered;
                            setDeviceForm(prev => ({ ...prev, selected_nodes: newSelection }));
                          }}
                          options={options}
                        />
                      </div>
                    );
                  })
                )}
              </div>
            </div>

          </div>

          <Button type="submit" className="w-full" loading={registerDevice.isPending}>
            Register Device
          </Button>
        </form>
      </Modal>

      {/* MODAL: CATALOG COMPONENT REGISTRATION (not available in PoC) */}
      <Modal
        open={openRegisterComponent}
        onClose={() => { setOpenRegisterComponent(false); setComponentName(""); }}
        title={`Register Global ${activeTab === "nodes" ? "Other Component" : activeTab.slice(0, -1)}`}
      >
        <div className="pt-4">
          <div className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-xl">
            <Info size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-400">Not Available in this PoC</p>
              <p className="text-xs text-amber-700 dark:text-amber-500 mt-1">
                Catalog management is planned for a future iteration.
              </p>
            </div>
          </div>
          <Button variant="outline" className="w-full mt-4" onClick={() => setOpenRegisterComponent(false)}>Close</Button>
        </div>
      </Modal>

      {/* MODAL: DEVICE SPEC VIEW */}
      <Modal open={!!selectedDevice} onClose={() => setSelectedDevice(null)} title="Device Specs & Live Inference" size="lg">
        {/* Tab Selection */}
        <div className="flex border-b border-gray-200 dark:border-gray-800 gap-4 mb-5">
          <button
            type="button"
            onClick={() => setModalTab("specs")}
            className={`pb-2.5 text-sm font-semibold border-b-2 transition-all ${modalTab === "specs"
                ? "border-blue-500 text-blue-600 dark:text-blue-400 font-bold"
                : "border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              }`}
          >
            See more
          </button>
          <button
            type="button"
            onClick={() => setModalTab("inference")}
            className={`pb-2.5 text-sm font-semibold border-b-2 transition-all ${modalTab === "inference"
                ? "border-blue-500 text-blue-600 dark:text-blue-400 font-bold"
                : "border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              }`}
          >
            Live Inference
          </button>
        </div>

        {modalTab === "specs" ? (
          <div className="space-y-6">
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase mb-2 tracking-wider block">Device Name / Label</label>
              <div className="flex gap-2">
                <Input
                  value={editingModalName}
                  onChange={(e) => setEditingModalName(e.target.value)}
                  className="flex-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg shadow-inner focus:ring-2 focus:ring-blue-500"
                  placeholder="Device label..."
                />
                <Button
                  type="button"
                  onClick={() => {
                    if (editingModalName.trim()) {
                      updateDeviceMutation.mutate({ id: selectedDevice.id, name: editingModalName.trim() });
                    }
                  }}
                  disabled={!editingModalName.trim() || editingModalName === selectedDevice?.name || updateDeviceMutation.isPending}
                  loading={updateDeviceMutation.isPending}
                  className="shrink-0"
                >
                  Save
                </Button>
              </div>
            </div>

            <div>
              <h4 className="text-[10px] font-bold text-gray-400 uppercase mb-2 tracking-wider">Hardware Type</h4>
              <Badge variant="default">{selectedDevice?.hardware_type ? resolveLabel(selectedDevice.hardware_type) : "—"}</Badge>
            </div>
            {(selectedDevice?.sensors?.length > 0 || selectedDevice?.actuators?.length > 0 || selectedDevice?.others?.length > 0) && (
              <div>
                <h4 className="text-[10px] font-bold text-gray-400 uppercase mb-2 tracking-wider">Attached Peripherals</h4>
                <div className="space-y-2">
                  {selectedDevice?.sensors?.map((s: any, i: number) => {
                    const name = s.name || s;
                    const Icon = getPeripheralIcon(name, Radio);
                    return (
                      <div key={i} className="flex justify-between items-center p-2 border rounded text-sm dark:border-gray-800">
                        <span className="flex items-center gap-2">
                          <Icon size={14} className="text-emerald-500" />
                          {resolveLabel(name)}
                        </span>
                        <Badge variant="success">Sensor</Badge>
                      </div>
                    );
                  })}
                  {selectedDevice?.actuators?.map((a: any, i: number) => {
                    const name = a.name || a;
                    const Icon = getPeripheralIcon(name, Zap);
                    return (
                      <div key={i} className="flex justify-between items-center p-2 border rounded text-sm dark:border-gray-800">
                        <span className="flex items-center gap-2">
                          <Icon size={14} className="text-yellow-500" />
                          {resolveLabel(name)}
                        </span>
                        <Badge variant="warning">Actuator</Badge>
                      </div>
                    );
                  })}
                  {selectedDevice?.others?.map((o: any, i: number) => {
                    const name = o.name || o;
                    const Icon = getPeripheralIcon(name, Server);
                    return (
                      <div key={i} className="flex justify-between items-center p-2 border rounded text-sm dark:border-gray-800">
                        <span className="flex items-center gap-2">
                          <Icon size={14} className="text-blue-500" />
                          {resolveLabel(name)}
                        </span>
                        <Badge variant="default">Other</Badge>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {!selectedDevice?.sensors?.length && !selectedDevice?.actuators?.length && !selectedDevice?.others?.length && (
              <p className="text-xs text-gray-500 italic">No peripheral components linked to this unit.</p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                <Activity size={16} className="text-blue-500 animate-pulse" /> Live Inference Stream
              </h4>
              <span className="text-[10px] font-mono text-gray-400 bg-gray-100 dark:bg-gray-850 px-2 py-0.5 rounded">
                2s polling
              </span>
            </div>

            {loadingInference ? (
              <div className="text-center py-8 text-xs text-gray-400 italic">Fetching predictions...</div>
            ) : inferenceResults.length === 0 ? (
              <div className="text-center py-10 border border-dashed rounded-xl flex flex-col items-center justify-center space-y-2">
                <Play size={24} className="text-gray-300 dark:text-gray-700" />
                <p className="text-sm font-bold text-gray-500 dark:text-gray-400">No predictions recorded</p>
                <p className="text-xs text-gray-400 max-w-xs text-center">
                  Verify that the edge agent is online and has a running script/model deployment executing inference.
                </p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                {inferenceResults.map((result: any, idx: number) => {
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
                    <Card key={idx} className="p-3 border border-gray-105 dark:border-gray-800 shadow-sm bg-gray-50/50 dark:bg-gray-900/40">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold font-mono text-gray-400">
                          {new Date(result.timestamp).toLocaleTimeString()}
                        </span>
                        <Badge variant="default" className="text-[9px] scale-90 origin-right">
                          dep: {result.deployment_id?.slice(0, 8) || "—"}
                        </Badge>
                      </div>

                      {hasDetections ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                          {detections.map((det: any, dIdx: number) => (
                            <div key={dIdx} className="flex items-center justify-between p-2 rounded-lg bg-white dark:bg-gray-950 border border-gray-100 dark:border-gray-800/80">
                              <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                                {det.class}
                              </span>
                              {det.confidence !== undefined ? (
                                <Badge variant="success" className="text-xs font-bold">
                                  {Math.round(det.confidence * 100)}%
                                </Badge>
                              ) : det.value !== undefined ? (
                                <span className="text-xs font-mono text-blue-500 font-bold truncate max-w-[80px]">
                                  {typeof det.value === "object" ? JSON.stringify(det.value) : String(det.value)}
                                </span>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-400 italic">No targets detected in this frame.</p>
                      )}
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
