"use client";
import { useState } from "react";
import Editor from "@monaco-editor/react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { Download, Save } from "lucide-react";

export function CodeEditorModal({ open, onClose, initialCode = "", name, language = "python" }: any) {
  const [code, setCode] = useState(initialCode);
  const [lang, setLang] = useState(language);

  const download = () => {
    const blob = new Blob([code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name || "script.py";
    a.click();
  };

  return (
    <Modal open={open} onClose={onClose} title={`Editing ${name}`} size="xl">
      <div className="flex gap-4 mb-4">
        <Select 
          value={lang} 
          onChange={(e) => setLang(e.target.value)} 
          options={[{value: 'python', label: 'Python'}, {value: 'java', label: 'Java'}, {value: 'cpp', label: 'C/C++'}]} 
        />
        <Button variant="outline" onClick={download}><Download size={16} className="mr-2"/> Download</Button>
      </div>
      
      <div className="h-[500px] border rounded-lg overflow-hidden">
        <Editor
          height="100%"
          language={lang}
          theme="vs-dark"
          value={code}
          onChange={(val) => setCode(val || "")}
        />
      </div>

      <div className="flex justify-end gap-3 mt-4">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={() => console.log("Save code:", code)}><Save size={16} className="mr-2"/> Save Script</Button>
      </div>
    </Modal>
  );
}