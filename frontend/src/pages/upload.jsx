import { useCallback, useRef, useState } from "react";
import {
  CheckCircle2,
  File,
  FileSpreadsheet,
  FileText,
  Loader2,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { cn } from "@/lib/utils";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function iconForFile(name) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "csv" || ext === "xlsx" || ext === "xls") return FileSpreadsheet;
  if (ext === "pdf" || ext === "doc" || ext === "docx") return FileText;
  return File;
}

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef(null);

  const addFiles = useCallback((list) => {
    if (!list || list.length === 0) return;
    const newFiles = Array.from(list).map((file) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
      name: file.name,
      size: file.size,
      status: "processing",
    }));

    setFiles((prev) => [...newFiles, ...prev]);

    newFiles.forEach((file) => {
      const delay = 1200 + Math.random() * 1200;
      setTimeout(() => {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === file.id ? { ...f, status: "indexed" } : f
          )
        );
      }, delay);
    });
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles]);

  const removeFile = (id) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const indexedCount = files.filter((f) => f.status === "indexed").length;

  return (
    <div className="container flex-1 px-4 py-12 sm:py-16">
      <div className="mx-auto max-w-3xl">
        <div className="text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-gray-200 px-4 py-1.5 font-body text-xs font-medium text-gray-800">
            Knowledge base ingestion
          </span>
          <h1 className="mt-5 font-sans text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            Upload your documents
          </h1>
          <p className="mt-3 font-body text-muted-foreground">
            Add files to the internal knowledge base. Once indexed, they'll
            be searchable from the AI assistant.
          </p>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "mt-10 flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-6 py-16 text-center transition-colors",
            isDragging
              ? "border-brand-blue bg-brand-blue/5"
              : "border-ink/15 bg-secondary/30 hover:border-ink/25 hover:bg-secondary/50"
          )}
        >
           <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-pink-500 text-white">
            <UploadCloud size={26} />
          </span>
          <div>
            <p className="font-sans text-base font-bold text-ink">Drag & drop files here</p>
            <p className="mt-1 font-body text-sm text-muted-foreground">
              or click to browse — PDF, DOCX, TXT, CSV and more
            </p>
          </div>

          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => addFiles(e.target.files)}
          />
        </div>

        {files.length > 0 && (
          <div className="mt-10">
            <div className="flex items-center justify-between">
              <h2 className="font-sans text-sm font-bold text-ink">
                Documents ({files.length})
              </h2>
              <p className="font-body text-xs text-muted-foreground">
                {indexedCount} of {files.length} indexed
              </p>
            </div>

            <ul className="mt-4 flex flex-col gap-2">
              {files.map((file) => {
                const Icon = iconForFile(file.name);
                return (
                  <li key={file.id} className="flex items-center gap-3 rounded-xl border border-ink/10 bg-white px-4 py-3 shadow-sm">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-ink">
                      <Icon size={18} />
                    </span>

                    <div className="min-w-0 flex-1">
                      <p className="truncate font-body text-sm font-medium text-ink">{file.name}</p>
                      <p className="font-body text-xs text-muted-foreground">{formatSize(file.size)}</p>
                    </div>

                    {file.status === "processing" ? (
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-secondary px-3 py-1 font-body text-xs font-medium text-muted-foreground">
                        <Loader2 size={12} className="animate-spin" />
                        Indexing
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-brand-blue/15 px-3 py-1 font-body text-xs font-medium text-ink">
                        <CheckCircle2 size={12} className="text-brand-pink" />
                        Indexed
                      </span>
                    )}

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(file.id);
                      }}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                      aria-label={`Remove ${file.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
