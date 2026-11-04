import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cn } from "cn"

const VARIANTS = {
  default: "d-badge-primary",
  secondary: "bg-base-200",
  destructive: "d-badge-error d-badge-soft",
  outline: "d-badge-outline border-base-300",
  ghost: "d-badge-ghost",
  link: "text-primary underline-offset-4 hover:underline",
}

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & { variant?: keyof typeof VARIANTS }) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(
          "d-badge d-badge-sm shrink-0 whitespace-nowrap [&>svg]:pointer-events-none [&>svg]:size-3!",
          VARIANTS[variant],
          className
        ),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge }
