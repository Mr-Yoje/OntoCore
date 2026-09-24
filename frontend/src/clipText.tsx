import type { ReactNode } from "react";

/** Single-line text: ellipsis when clipped, full text on hover. */
export function ClipText({
  text,
  className,
}: {
  text: string;
  className?: string;
}): ReactNode {
  const value = text || "";
  return (
    <span className={className ? `cell-ellipsis ${className}` : "cell-ellipsis"} title={value || undefined}>
      {value}
    </span>
  );
}
