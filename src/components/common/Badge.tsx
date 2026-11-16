import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import type {
  FieldVerificationStatus,
  InvoiceStatus,
  SupplierStatus,
} from '../../types/domain';

export function StatusBadge({
  status,
}: {
  status: InvoiceStatus | FieldVerificationStatus | SupplierStatus;
}) {
  if (status === 'Verified') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 whitespace-nowrap">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
        <span>{status}</span>
      </span>
    );
  }

  if (status === 'Flagged') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-700 whitespace-nowrap">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-rose-600" />
        <span>{status}</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 whitespace-nowrap">
      <Clock className="h-3.5 w-3.5 shrink-0 text-amber-600" />
      <span>{status}</span>
    </span>
  );
}
