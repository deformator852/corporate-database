import * as React from "react"
import { cn } from "cn"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn("d-textarea w-full min-w-0 aria-invalid:border-error", className)}
      {...props}
    />
  )
}

export { Textarea }
