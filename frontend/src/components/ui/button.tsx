import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cn } from "cn"

const VARIANTS = {
  default: "d-btn-primary",
  outline: "d-btn-outline border-base-300",
  secondary: "",
  ghost: "d-btn-ghost",
  destructive: "d-btn-error d-btn-soft",
  link: "d-btn-link",
}

const SIZES = {
  default: "",
  xs: "d-btn-xs",
  sm: "d-btn-sm",
  lg: "d-btn-lg",
  icon: "d-btn-square",
  "icon-xs": "d-btn-square d-btn-xs [&_svg:not([class*='size-'])]:size-3.5",
  "icon-sm": "d-btn-square d-btn-sm",
  "icon-lg": "d-btn-square d-btn-lg",
}

type ButtonStyle = {
  variant?: keyof typeof VARIANTS
  size?: keyof typeof SIZES
  className?: string
}

function buttonVariants({ variant = "default", size = "default", className }: ButtonStyle = {}) {
  return cn(
    "d-btn flex-nowrap whitespace-nowrap [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    VARIANTS[variant],
    SIZES[size],
    className
  )
}

function Button({
  className,
  variant,
  size,
  ...props
}: Omit<ButtonPrimitive.Props, "className"> & ButtonStyle) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={buttonVariants({ variant, size, className })}
      {...props}
    />
  )
}

export { Button, buttonVariants }
