"use client";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { getScripts, deleteScript, uploadScript, getHardwareTypes, getLibraries, LibraryGroup } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { HW_LABELS } from "@/lib/utils";
import {
  Code2, Plus, Trash2, FileCode, ArrowLeft, Save,
  Loader2, Upload, Download, BookOpen, Info, Package,
} from "lucide-react";

const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="h-[500px] flex items-center justify-center bg-gray-900 text-white">
      <Loader2 className="animate-spin mr-2" /> Loading Editor...
    </div>
  ),
});

const SCRIPT_TEMPLATE = `"""
AURA Edge Script Template
=========================
Implement pre_inference() and post_inference().
Demonstrates importing the generic camera library and inference runtime.
"""
from __future__ import annotations
import numpy as np
from aura_hw import execute_inference, get_model_classes
from hardware.sensors.camera.library import take_photo

# Example template library imports:
# from hardware.sensors.template.library import read_value
# from hardware.actuators.template.library import write_value

INPUT_WIDTH  = 640
INPUT_HEIGHT = 640
CONF_THRESHOLD = 0.5
CLASSES = ["person", "car", "dog"]  # Adjust to your labels


def pre_inference(raw_input) -> np.ndarray:
    """Preprocess raw input (RGB frame) -> numpy tensor ready for the model."""
    import cv2
    img = cv2.resize(raw_input, (INPUT_WIDTH, INPUT_HEIGHT))
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))   # HWC -> CHW
    return np.expand_dims(img, axis=0)   # -> NCHW


def post_inference(raw_output) -> list[dict]:
    """Postprocess model output -> list of detection dicts."""
    detections = []
    outputs = list(raw_output.values())[0] if isinstance(raw_output, dict) else raw_output
    if outputs is None or len(outputs) == 0:
        return detections
    
    classes = get_model_classes()
    if not classes:
        classes = CLASSES

    for box in outputs[0].T:
        scores = box[4:]
        class_id = int(np.argmax(scores))
        confidence = float(scores[class_id])
        if confidence < CONF_THRESHOLD:
            continue
        cx, cy, w, h = box[:4]
        detections.append({
            "class": classes[class_id] if class_id < len(classes) else str(class_id),
            "confidence": round(confidence, 3),
            "bbox": [float(cx), float(cy), float(w), float(h)],
        })
    return detections


def run(raw_input=None) -> list[dict]:
    """
    Main entrypoint called by the runtime.
    Captures a frame from the generic camera library if raw_input is not passed.
    """
    frame = raw_input if raw_input is not None else take_photo()
    
    # Run pre-inference on the frame
    model_input = pre_inference(frame)
    
    # Perform inference using the generic inference function
    model_output = execute_inference(model_input)
    
    # Parse results in post-inference
    return post_inference(model_output)
`;

// Category display labels and icons
const CATEGORY_LABELS: Record<string, string> = {
  sensors: "Sensors",
  actuators: "Actuators",
  others: "Others",
  hw_arch: "Inference",
};

export default function ScriptsPage() {
  const qc = useQueryClient();

  const { data: hardwareTypes = [] } = useQuery({
    queryKey: ["hardwareTypes"],
    queryFn: getHardwareTypes,
  });

  const hwOptions = hardwareTypes.map(v => ({ value: v, label: HW_LABELS[v] || v }));

  const { data: scripts = [], isLoading } = useQuery({ queryKey: ["scripts"], queryFn: getScripts });

  // Fetch dynamic hardware libraries
  const { data: hwLibraries = [] } = useQuery<LibraryGroup[]>({
    queryKey: ["libraries"],
    queryFn: getLibraries,
  });

  // Sort libraries to make sure "hw_arch" (Inference) is first
  const sortedLibraries = [...hwLibraries].sort((a, b) => {
    if (a.category === "hw_arch" && b.category !== "hw_arch") return -1;
    if (a.category !== "hw_arch" && b.category === "hw_arch") return 1;
    return 0;
  });

  const [editingScript, setEditingScript] = useState<any | null>(null);
  const [code, setCode] = useState("");
  const [lang, setLang] = useState("python");

  // Upload modal state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ name: "", description: "", language: "python" });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const uploadFileRef = useRef<HTMLInputElement>(null);

  // Dedicated Save Script states (for editor)
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveForm, setSaveForm] = useState({ name: "", description: "", language: "python" });
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  const editorFileRef = useRef<HTMLInputElement>(null);

  const remove = useMutation({
    mutationFn: (id: string) => deleteScript(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scripts"] }),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!uploadFile) throw new Error("No file selected");
      return uploadScript(uploadForm.name, uploadForm.description, uploadFile, uploadForm.language);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scripts"] });
      setUploadOpen(false);
      setUploadFile(null);
    },
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      let ext = ".py";
      if (saveForm.language === "cpp") ext = ".cpp";
      else if (saveForm.language === "java") ext = ".java";

      const fileName = saveForm.name.endsWith(ext) ? saveForm.name : `${saveForm.name}${ext}`;
      const blob = new Blob([code], { type: "text/plain" });
      const file = new File([blob], fileName, { type: "text/plain" });

      setSaveStatus("saving");
      return uploadScript(saveForm.name, saveForm.description, file, saveForm.language);
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["scripts"] });
      setSaveStatus("success");
      if (data && data.id) {
        setEditingScript(data);
      }
    },
    onError: (err: any) => {
      setSaveStatus("error");
      setErrorMessage(err.message || "An error occurred while saving the script.");
    }
  });

  // Local editor file loaders
  const handleEditorFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (evt) => {
        setCode(evt.target?.result as string || "");
      };
      reader.readAsText(file);
    }
  };

  const saveFromEditor = () => {
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = editingScript.name || "script.py";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleSaveToPlatformClick = () => {
    setSaveForm({
      name: editingScript.name.replace(/\.[^/.]+$/, ""),
      description: editingScript.description || "",
      language: lang
    });
    setSaveStatus("idle");
    setSaveModalOpen(true);
  };

  const openNewScript = () => {
    setCode(SCRIPT_TEMPLATE);
    setLang("python");
    setEditingScript({
      id: "new",
      name: "new_inference_script.py",
      description: "Custom pre/post inference pipeline",
      content: SCRIPT_TEMPLATE,
    });
  };

  // Auto-detect language from extension
  const handleUploadFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setUploadFile(file);
    if (file) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      let detectedLang = "python";
      if (ext === "cpp" || ext === "cc" || ext === "h" || ext === "hpp") detectedLang = "cpp";
      else if (ext === "java") detectedLang = "java";
      setUploadForm(f => ({ ...f, language: detectedLang }));
    }
  };

  const showRealDocs = sortedLibraries.length > 0;

  return (
    <div className="w-full max-w-[1600px] mx-auto animate-fade-in px-4 sm:px-6 lg:px-12 py-8">
      {editingScript ? (
        <div className="h-[calc(100vh-80px)] flex flex-col animate-fade-in -mx-4 sm:-mx-6 lg:-mx-12 -my-8">
          <div className="flex items-center justify-between px-6 py-4 border-b dark:border-gray-800 bg-white/50 dark:bg-gray-950/50 backdrop-blur-md">
            <div className="flex items-center gap-4">
              <Button variant="ghost" onClick={() => setEditingScript(null)}><ArrowLeft size={18} /></Button>
              <h2 className="text-lg font-bold">{editingScript.name}</h2>
              <div className="w-40">
                <Select value={lang} onChange={e => setLang(e.target.value)}
                  options={[{ value: "python", label: "Python" }, { value: "cpp", label: "C++" }, { value: "java", label: "Java" }]} />
              </div>
            </div>
            <div className="flex gap-2 items-center">
              <div className="hidden md:flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-800/50 mr-2">
                <Info size={12} /> Save to Platform creates a new script version
              </div>
              <input type="file" ref={editorFileRef} className="hidden" accept=".py,.cpp,.java" onChange={handleEditorFileUpload} />
              <Button variant="outline" size="sm" onClick={() => editorFileRef.current?.click()}>
                <Upload size={14} className="mr-2" /> Load Local
              </Button>
              <Button variant="outline" size="sm" onClick={saveFromEditor}>
                <Download size={14} className="mr-2" /> Download
              </Button>
              <Button size="sm" className="bg-orange-600 hover:bg-orange-700" onClick={handleSaveToPlatformClick}>
                <Save size={14} className="mr-2" /> Save to Platform
              </Button>
            </div>
          </div>

          <div className="flex flex-1 overflow-hidden">
            <div className="flex-1 border-r dark:border-gray-800">
              <Editor height="100%" language={lang} theme="vs-dark" value={code} onChange={v => setCode(v || "")} />
            </div>
            {showRealDocs && (
              <div className="w-80 bg-gray-50 dark:bg-gray-950 p-6 overflow-y-auto hidden lg:block">
                <div className="flex items-center gap-2 mb-6 text-orange-500 font-bold">
                  <BookOpen size={20} /> Hardware Libraries
                </div>
                <div className="space-y-5">
                  {sortedLibraries.map((lib, i) => (
                    <div key={i} className="space-y-2">
                      <div className="flex items-center gap-2 mb-1">
                        <Package size={14} className="text-orange-400" />
                        <span className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                          {CATEGORY_LABELS[lib.category] || lib.category} / {lib.subcategory}
                        </span>
                      </div>
                      <code className="block text-[11px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1 rounded break-all">
                        from {lib.import_path} import ...
                      </code>
                      {lib.api.map((fn, j) => (
                        <div key={j} className="space-y-0.5 pl-2 border-l-2 border-gray-200 dark:border-gray-700">
                          <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                            {fn.name}
                          </code>
                          {fn.desc && (
                            <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">{fn.desc}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-orange-500 mb-2">
                Scripts
              </h1>
              <p className="text-gray-600 dark:text-gray-400">
                Manage inference logic and HAL integration scripts.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={() => setUploadOpen(true)} className="gap-2 shrink-0 border-gray-200 dark:border-gray-800">
                <Upload size={16} /> Upload File
              </Button>
              <Button onClick={openNewScript} className="gap-2 shrink-0">
                <Code2 size={16} /> Write Script
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Scripts list */}
            <div className="lg:col-span-2 space-y-4">
              {isLoading ? (
                <div className="text-center py-10 text-gray-500">Loading scripts...</div>
              ) : scripts.length === 0 ? (
                <Card className="border-dashed border-2 bg-transparent shadow-none opacity-60">
                  <div className="flex flex-col sm:flex-row items-center justify-between p-4 gap-4">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center border border-gray-200 dark:border-gray-700">
                        <FileCode size={20} className="text-gray-400" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-base font-bold text-gray-500 dark:text-gray-400">Empty Script Slot</span>
                          <Badge variant="muted">N/A</Badge>
                        </div>
                        <p className="text-xs text-gray-400">No logic defined</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <Button variant="outline" size="sm" className="gap-2 w-full sm:w-auto" onClick={() => setUploadOpen(true)}>
                        <Upload size={14} /> Upload File
                      </Button>
                      <Button size="sm" className="gap-2 w-full sm:w-auto" onClick={openNewScript}>
                        <Code2 size={14} /> Write Script
                      </Button>
                    </div>
                  </div>
                </Card>
              ) : (
                scripts.map((s: any) => (
                  <Card key={s.id} className="flex justify-between items-center p-5 hover:border-orange-400 transition-all">
                    <div className="flex items-center gap-4">
                      <FileCode className="text-orange-500" />
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-bold">{s.name}</p>
                          <Badge variant="muted" className="capitalize text-[10px] py-0 px-1.5">{s.language || "python"}</Badge>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => { setEditingScript(s); setCode(s.content || SCRIPT_TEMPLATE); }}
                      >
                        Edit
                      </Button>
                      <button
                        onClick={() => remove.mutate(s.id)}
                        className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </Card>
                ))
              )}
            </div>

            {/* HAL Documentation / Hardware Libraries */}
            <div className="lg:col-span-1">
              <Card className="p-6 sticky top-8 border-t-4 border-t-orange-500">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-bold flex items-center gap-2 text-gray-900 dark:text-white">
                    <BookOpen size={18} className="text-orange-500" />
                    Hardware Libraries
                  </h2>
                </div>
                <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
                  {sortedLibraries.length === 0 ? (
                    <p className="text-sm text-gray-500 italic">
                      No hardware libraries found. Libraries are scanned from the hardware/ directory.
                    </p>
                  ) : (
                    sortedLibraries.map((lib, i) => (
                      <div key={i} className="space-y-2 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
                        <div className="flex items-center gap-2">
                          <Package size={14} className="text-orange-400 shrink-0" />
                          <span className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                            {CATEGORY_LABELS[lib.category] || lib.category} / {lib.subcategory}
                          </span>
                        </div>
                        <code className="block text-[11px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1.5 rounded break-all">
                          from {lib.import_path} import ...
                        </code>
                        <div className="space-y-2 mt-1">
                          {lib.api.map((fn, j) => (
                            <div key={j} className="pl-2 border-l-2 border-gray-200 dark:border-gray-700">
                              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                                {fn.name}
                              </code>
                              {fn.desc && (
                                <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed mt-0.5">{fn.desc}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Upload modal */}
      <Modal open={uploadOpen} onClose={() => { setUploadOpen(false); setUploadFile(null); }} title="Save Script">
        <form onSubmit={e => { e.preventDefault(); if (uploadFile) uploadMutation.mutate(); }} className="flex flex-col gap-5 pt-4">
          <Input
            label="Script name"
            value={uploadForm.name}
            onChange={e => setUploadForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. yolov8-hailo-postprocess"
            required
          />
          <Input
            label="Description (optional)"
            value={uploadForm.description}
            onChange={e => setUploadForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Brief description..."
          />
          <Select
            label="Script language"
            value={uploadForm.language}
            onChange={e => setUploadForm(f => ({ ...f, language: e.target.value }))}
            options={[
              { value: "python", label: "Python" },
              { value: "cpp", label: "C++" },
              { value: "java", label: "Java" }
            ]}
          />
          <div
            className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl p-8 flex flex-col items-center cursor-pointer hover:border-orange-400 transition-colors"
            onClick={() => uploadFileRef.current?.click()}
          >
            <Upload size={28} className="text-gray-400 mb-2" />
            <p className="text-sm text-gray-500">
              {uploadFile ? <span className="text-orange-500 font-medium">{uploadFile.name}</span> : "Click to upload script file"}
            </p>
            <input ref={uploadFileRef} type="file" accept=".py,.cpp,.java" className="hidden" onChange={handleUploadFileChange} />
          </div>
          <Button type="submit" className="w-full" disabled={!uploadFile || uploadMutation.isPending} loading={uploadMutation.isPending}>
            Upload to Platform
          </Button>
        </form>
      </Modal>

      {/* Save Script Modal (with loading / success state and options for user) */}
      <Modal open={saveModalOpen} onClose={() => { if (saveStatus !== "saving") setSaveModalOpen(false); }} title={saveStatus === "success" ? "Saved Successfully" : "Save Script"}>
        {saveStatus === "idle" && (
          <form onSubmit={e => { e.preventDefault(); saveMutation.mutate(); }} className="flex flex-col gap-5 pt-4">
            <Input
              label="Script name"
              value={saveForm.name}
              onChange={e => setSaveForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. yolov8-hailo-postprocess"
              required
            />
            <Input
              label="Description (optional)"
              value={saveForm.description}
              onChange={e => setSaveForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Brief description..."
            />
            <Select
              label="Script language"
              value={saveForm.language}
              onChange={e => setSaveForm(f => ({ ...f, language: e.target.value }))}
              options={[
                { value: "python", label: "Python" },
                { value: "cpp", label: "C++" },
                { value: "java", label: "Java" }
              ]}
            />
            <div className="flex gap-3 justify-end pt-2">
              <Button type="button" variant="outline" onClick={() => setSaveModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" className="bg-orange-600 hover:bg-orange-700">
                Confirm & Save
              </Button>
            </div>
          </form>
        )}

        {saveStatus === "saving" && (
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <Loader2 className="h-10 w-10 animate-spin text-orange-500" />
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              Saving script to platform...
            </p>
          </div>
        )}

        {saveStatus === "success" && (
          <div className="flex flex-col items-center justify-center py-8 text-center animate-fade-in">
            <div className="h-16 w-16 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-500 border border-emerald-200 dark:border-emerald-800 rounded-full flex items-center justify-center mb-4">
              <svg className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
              Script Saved!
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-sm">
              Your changes have been successfully committed to the AURA platform.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 w-full justify-center">
              <Button 
                variant="outline"
                className="w-full sm:w-auto"
                onClick={() => {
                  setSaveModalOpen(false);
                  setEditingScript(null); // Back to scripts list
                }}
              >
                Back to Scripts List
              </Button>
              <Button 
                className="w-full sm:w-auto bg-orange-600 hover:bg-orange-700"
                onClick={() => {
                  setSaveModalOpen(false); // Continue editing
                }}
              >
                Continue Editing
              </Button>
            </div>
          </div>
        )}

        {saveStatus === "error" && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="h-16 w-16 bg-red-50 dark:bg-red-900/20 text-red-500 border border-red-200 dark:border-red-800 rounded-full flex items-center justify-center mb-4">
              <svg className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
              Save Failed
            </h3>
            <p className="text-sm text-red-500 mb-6 max-w-sm">
              {errorMessage}
            </p>
            <div className="flex gap-3 w-full justify-center">
              <Button 
                variant="outline"
                onClick={() => setSaveStatus("idle")}
              >
                Try Again
              </Button>
              <Button 
                className="bg-gray-600"
                onClick={() => setSaveModalOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}