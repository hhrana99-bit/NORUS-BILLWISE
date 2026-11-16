import { FileUp, Info, Upload, X } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from 'react';
import { createDemoUploadedInvoice } from '../../services/invoiceService';
import { useWorkspace } from '../../state/WorkspaceContext';

const ACCEPTED_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp'];

export function UploadInvoiceModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { suppliers, addUploadedInvoice, selectInvoiceForReview } = useWorkspace();
  const inputRef = useRef<HTMLInputElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [supplierName, setSupplierName] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (!open) return;
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const validateAndSetFile = (file: File | undefined) => {
    setErrorMsg('');
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setErrorMsg('Please select a PDF, PNG, JPG, or WEBP file.');
      return;
    }
    setSelectedFile(file);
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    validateAndSetFile(e.target.files?.[0]);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    validateAndSetFile(e.dataTransfer.files?.[0]);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg('Select a sample PDF or image file to stage in the local workspace.');
      return;
    }

    const previewUrl = URL.createObjectURL(selectedFile);
    const created = createDemoUploadedInvoice({
      file: selectedFile,
      previewUrl,
      supplierName,
      invoiceNumber,
      suppliers,
    });

    addUploadedInvoice(created);
    setSelectedFile(null);
    setSupplierName('');
    setInvoiceNumber('');
    onClose();
    selectInvoiceForReview(created.id);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
              <Upload className="h-4 w-4" />
            </div>
            <div>
              <h2 id="upload-modal-title" className="text-sm font-semibold text-slate-900">
                Upload Supplier Invoice (Local Demo)
              </h2>
              <p className="text-xs text-slate-500">
                Stage PDF or image files into the Pending Review queue
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            aria-label="Close modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-5 sm:p-6">
          <div className="flex items-start gap-2.5 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3 text-xs text-indigo-950">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
            <p className="leading-relaxed">
              <strong>Frontend Prototype Notice:</strong> Selected files are previewed
              locally in your browser only. No server upload, OCR, or AI extraction runs
              in Task 001. Do not upload real confidential customer invoices.
            </p>
          </div>

          <div
            role="button"
            tabIndex={0}
            aria-label="Choose a PDF or image file to stage locally"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed p-5 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 sm:p-6 ${
              isDragging
                ? 'border-indigo-500 bg-indigo-50/50'
                : 'border-slate-300 bg-slate-50/60 hover:border-indigo-400 hover:bg-slate-50'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/webp"
              onChange={handleFileChange}
              className="hidden"
            />
            <FileUp className="mx-auto h-8 w-8 text-slate-400" />
            {selectedFile ? (
              <div className="mt-3">
                <p className="break-all text-sm font-medium text-slate-900">
                  {selectedFile.name}
                </p>
                <p className="mt-0.5 font-mono text-xs text-slate-500 tabular-nums">
                  {(selectedFile.size / 1024).toFixed(1)} KB · Ready to stage locally
                </p>
              </div>
            ) : (
              <div className="mt-3">
                <p className="text-sm font-medium text-slate-700">
                  Click to choose a PDF or image, or drag and drop
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Supports PDF, PNG, JPG, WEBP
                </p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-slate-700">
                Reference Supplier Name (Optional)
              </label>
              <input
                type="text"
                list="known-suppliers-list"
                value={supplierName}
                onChange={(e) => setSupplierName(e.target.value)}
                placeholder="e.g. Sample Logistics LLP"
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
              <datalist id="known-suppliers-list">
                {suppliers.map((sup) => (
                  <option key={sup.id} value={sup.name} />
                ))}
              </datalist>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">
                Reference Invoice No. (Optional)
              </label>
              <input
                type="text"
                value={invoiceNumber}
                onChange={(e) => setInvoiceNumber(e.target.value)}
                placeholder="e.g. DEMO-2026-01"
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
            </div>
          </div>

          {errorMsg && (
            <p className="text-xs font-medium text-rose-600">{errorMsg}</p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 whitespace-nowrap"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap"
            >
              <Upload className="h-3.5 w-3.5" />
              Stage &amp; Open in Review Centre
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
