import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "group/badge inline-flex h-[22px] w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-md border border-transparent px-2 py-0 text-[11px] font-semibold tracking-[0.04em] whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline:
          "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost:
          "hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      /* Domain tones. A badge states a fact and the word is always present inside it,
         so the colour reinforces the rating rather than carrying it. A soft filled chip
         reads as a verdict at a glance, which is what a non-specialist needs. */
      tone: {
        neutral: "bg-surface-sunk text-muted-foreground",
        brand: "bg-brand-wash text-ink",
        buy: "bg-buy-wash text-buy",
        hold: "bg-hold-wash text-hold",
        sell: "bg-sell-wash text-sell",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  tone,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  // A tone supplies its own ground and border, so it replaces the variant rather than
  // layering on top of one — passing both would paint a rating badge over bg-primary.
  const resolved = tone ? undefined : (variant ?? "default")

  return (
    <Comp
      data-slot="badge"
      data-variant={resolved}
      data-tone={tone}
      className={cn(badgeVariants({ variant: resolved, tone }), className)}
      {...props}
    />
  )
}

/** Maps a rating to its tone. Kept here so the mapping lives next to the colours. */
function ratingTone(rating?: string | null) {
  if (rating === "BUY") return "buy" as const
  if (rating === "SELL") return "sell" as const
  if (rating === "HOLD") return "hold" as const
  return "neutral" as const
}

export { Badge, badgeVariants, ratingTone }
