import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  File,
  FileSpreadsheet,
  FileText,
  Loader2,
  Trash2,
  UploadCloud,
  RefreshCw,
  AlertCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadFiles, listDocuments, deleteDocument, replaceDocument, ingestUrl } from "@/lib/api";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function iconForFile(name) {
  const ext = (name || "").split(".").pop()?.toLowerCase();
  if (ext === "csv" || ext === "xlsx" || ext === "xls") return FileSpreadsheet;
  if (ext === "pdf" || ext === "doc" || ext === "docx") return FileText;
  return File;
}

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const inputRef = useRef(null);
  const replaceInputRef = useRef(null);
  const [replacingDocId, setReplacingDocId] = useState(null);
  const [urlInput, setUrlInput] = useState("");
  const [isUrlLoading, setIsUrlLoading] = useState(false);
  const pollingRef = useRef(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      setIsLoading(true);
      const docs = await listDocuments();
      setFiles(docs.map(doc => ({
        id: doc.doc_id,
        name: doc.name,
        size: doc.size,
        status: doc.status || "indexed",
        chunk_count: doc.chunk_count,
        uploaded_at: doc.uploaded_at
      })).reverse());
    } catch (err) {
      console.error("Failed to load documents", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadFiles = async (fileList) => {
    if (!fileList || fileList.length === 0) return;
    
    // Add temp files for UI
    const tempFiles = Array.from(fileList).map(file => ({
      id: `temp-${Date.now()}-${Math.random()}`,
      name: file.name,
      size: file.size,
      status: "processing",
      rawFile: file
    }));
    
    setFiles(prev => [...tempFiles, ...prev]);

    // Upload in background
    for (const tempFile of tempFiles) {
      try {
        const results = await uploadFiles([tempFile.rawFile]);
        const result = results[0];
        
        setFiles(prev => prev.map(f => {
          if (f.id === tempFile.id) {
             if (result.status === "error") {
               return { ...f, status: "error", error: result.error };
             }
             return {
               id: result.doc_id,
               name: result.name,
               size: result.size,
               status: "indexed",
               chunk_count: result.chunk_count,
               uploaded_at: result.uploaded_at
             };
          }
          return f;
        }));
      } catch (err) {
        console.error("Upload failed for", tempFile.name, err);
        setFiles(prev => prev.map(f => 
          f.id === tempFile.id ? { ...f, status: "error", error: err.message } : f
        ));
      }
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    handleUploadFiles(e.dataTransfer.files);
  }, []);

  const handleRemove = async (id, e) => {
    e.stopPropagation();
    
    // If it's a temp file or error file, just remove from UI
    if (id.startsWith("temp-")) {
      setFiles(prev => prev.filter(f => f.id !== id));
      return;
    }

    try {
      setFiles(prev => prev.map(f => f.id === id ? { ...f, status: "deleting" } : f));
      await deleteDocument(id);
      setFiles(prev => prev.filter(f => f.id !== id));
    } catch (err) {
      console.error("Failed to delete document", err);
      // Revert status on failure
      setFiles(prev => prev.map(f => f.id === id ? { ...f, status: "error", error: "Failed to delete" } : f));
    }
  };

  const handleReplaceClick = (id, e) => {
    e.stopPropagation();
    setReplacingDocId(id);
    replaceInputRef.current?.click();
  };

  const handleReplaceSubmit = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !replacingDocId) return;
    
    e.target.value = ''; // Reset input
    
    try {
      setFiles(prev => prev.map(f => f.id === replacingDocId ? { ...f, status: "processing", name: file.name, size: file.size } : f));
      const result = await replaceDocument(replacingDocId, file);
      
      setFiles(prev => prev.map(f => {
        if (f.id === replacingDocId) {
           return {
             id: result.doc_id,
             name: result.name,
             size: result.size,
             status: "indexed",
             chunk_count: result.chunk_count,
             uploaded_at: result.uploaded_at
           };
        }
        return f;
      }));
    } catch (err) {
      console.error("Failed to replace document", err);
      setFiles(prev => prev.map(f => f.id === replacingDocId ? { ...f, status: "error", error: "Failed to replace" } : f));
    } finally {
      setReplacingDocId(null);
    }
  };

  const pollJobStatus = (jobId, tempId) => {
    const poll = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"}/ingest/jobs/${jobId}`);
        const job = await res.json();
        if (job.status === "completed" || job.status === "failed") {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
          setFiles(prev => prev.map(f => {
            if (f.id === tempId) {
              if (job.status === "failed") {
                return { ...f, status: "error", error: job.error || "Ingest failed" };
              }
              return {
                id: `job-${jobId}`,
                name: f.name,
                size: 0,
                status: "indexed",
                chunk_count: job.chunk_count,
              };
            }
            return f;
          }));
        }
      } catch {
        // ignore poll errors, keep trying
      }
    };
    pollingRef.current = setInterval(poll, 3000);
  };

  const handleUrlSubmit = async (e) => {
    e.preventDefault();
    if (!urlInput.trim()) return;

    const url = urlInput.trim();
    setUrlInput("");
    
    // Add temp file for UI
    const tempId = `temp-url-${Date.now()}`;
    const tempFile = {
      id: tempId,
      name: (() => { try { return new URL(url).hostname; } catch { return url.slice(0, 40); } })() || "Scraping URL...",
      size: 0,
      status: "processing",
    };
    
    setFiles(prev => [tempFile, ...prev]);
    setIsUrlLoading(true);

    try {
      const result = await ingestUrl(url);
      
      // Background job (HuggingFace datasets)
      if (result.job_id) {
        setFiles(prev => prev.map(f => {
          if (f.id === tempId) {
            return { ...f, name: `${f.name} (background)` };
          }
          return f;
        }));
        pollJobStatus(result.job_id, tempId);
        return;
      }

      // Synchronous response (regular URLs)
      setFiles(prev => prev.map(f => {
        if (f.id === tempId) {
           return {
             id: result.doc_id,
             name: result.name,
             size: result.size,
             status: "indexed",
             chunk_count: result.chunk_count,
             uploaded_at: result.uploaded_at
           };
        }
        return f;
      }));
    } catch (err) {
      console.error("URL Ingest failed", err);
      setFiles(prev => prev.map(f => 
        f.id === tempId ? { ...f, status: "error", error: err.message } : f
      ));
    } finally {
      setIsUrlLoading(false);
    }
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
              or click to browse — PDF, DOCX, TXT, CSV
            </p>
          </div>

          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt,.csv"
            className="hidden"
            onChange={(e) => handleUploadFiles(e.target.files)}
          />
          <input
            ref={replaceInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.csv"
            className="hidden"
            onChange={handleReplaceSubmit}
          />
        </div>

        {/* URL Input Form */}
        <form onSubmit={handleUrlSubmit} className="mt-6 flex items-center gap-3">
            <div className="flex-1">
                <input
                    type="url"
                    placeholder="Or paste a Hugging Face link (or any URL) to ingest..."
                    className="w-full rounded-xl border border-ink/10 bg-white px-4 py-3 font-body text-sm text-ink placeholder:text-muted-foreground focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    disabled={isUrlLoading}
                    required
                />
            </div>
            <button
                type="submit"
                disabled={isUrlLoading || !urlInput.trim()}
                className="flex items-center gap-2 rounded-xl bg-gray-900 px-6 py-3 font-sans text-sm font-semibold text-white transition-colors hover:bg-gray-800 disabled:opacity-50"
            >
                {isUrlLoading ? <Loader2 size={18} className="animate-spin" /> : "Ingest URL"}
            </button>
        </form>

        {isLoading ? (
            <div className="mt-10 flex justify-center py-8">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
        ) : files.length > 0 && (
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
                      <p className="truncate font-body text-sm font-medium text-ink">{file.name || "Untitled"}</p>
                      <p className="font-body text-xs text-muted-foreground">
                        {formatSize(file.size || 0)} 
                        {file.chunk_count !== undefined && ` • ${file.chunk_count} chunks`}
                      </p>
                    </div>

                    {file.status === "processing" ? (
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-secondary px-3 py-1 font-body text-xs font-medium text-muted-foreground">
                        <Loader2 size={12} className="animate-spin" />
                        Indexing
                      </span>
                    ) : file.status === "deleting" ? (
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-secondary px-3 py-1 font-body text-xs font-medium text-muted-foreground">
                        <Loader2 size={12} className="animate-spin" />
                        Deleting
                      </span>
                    ) : file.status === "error" ? (
                       <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-red-100 px-3 py-1 font-body text-xs font-medium text-red-600">
                        <AlertCircle size={12} />
                        Error
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-brand-blue/15 px-3 py-1 font-body text-xs font-medium text-ink">
                        <CheckCircle2 size={12} className="text-brand-pink" />
                        Indexed
                      </span>
                    )}

                    <div className="flex items-center gap-1 ml-2">
                        <button
                        onClick={(e) => handleReplaceClick(file.id, e)}
                        disabled={file.status === "processing" || file.status === "deleting"}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-ink disabled:opacity-50"
                        title="Replace document"
                        >
                        <RefreshCw size={15} />
                        </button>
                        <button
                        onClick={(e) => handleRemove(file.id, e)}
                        disabled={file.status === "processing" || file.status === "deleting"}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                        title={`Remove ${file.name}`}
                        >
                        <Trash2 size={15} />
                        </button>
                    </div>
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
