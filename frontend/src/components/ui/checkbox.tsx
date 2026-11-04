import * as React from "react"
import { cn } from "cn"

function Checkbox({
  className,
  onCheckedChange,
  ...props
}: Omit<React.ComponentProps<"input">, "type" | "onChange"> & {
  onCheckedChange?: (checked: boolean) => void
}) {
  return (
    <input
      type="checkbox"
      data-slot="checkbox"
      className={cn("d-checkbox d-checkbox-sm d-checkbox-primary", className)}
      onChange={(event) => onCheckedChange?.(event.target.checked)}
      {...props}
    />
  )
}

export { Checkbox }
