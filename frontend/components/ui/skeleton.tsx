import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

/** Skeletons match the final layout. A spinner says something is loading; a skeleton
 *  in the shape of a table says a table is loading, so the page does not jump. */
function SkeletonTable({ rows = 8 }: { rows?: number }) {
  return (
    <div className="panel overflow-hidden" aria-hidden>
      <div className="flex items-center gap-4 border-b border-rule px-3 py-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="ml-auto h-3 w-14" />
        <Skeleton className="h-3 w-14" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 border-b border-rule-soft px-3 py-3 last:border-0"
        >
          <Skeleton className="h-3" style={{ width: `${30 + ((i * 13) % 40)}%` }} />
          <Skeleton className="ml-auto h-3 w-16" />
          <Skeleton className="h-3 w-10" />
        </div>
      ))}
    </div>
  )
}

export { Skeleton, SkeletonTable }
