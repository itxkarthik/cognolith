import { LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils/cn";

interface LoadingSpinnerProps {
  className?: string;
  label?: string;
  showLabel?: boolean;
}

export function LoadingSpinner({
  className,
  label = "Loading",
  showLabel = false,
}: LoadingSpinnerProps) {
  return (
    <div className={cn("inline-flex items-center gap-2", className)}>
      <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
      {showLabel && <span className="text-sm">{label}</span>}
    </div>
  );
}
