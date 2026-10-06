/** One `cn`, two import paths.
 *
 *  The project imported `@/lib/cn` long before shadcn arrived and vendored its
 *  components against `@/lib/utils`. Re-exporting keeps a single implementation
 *  rather than two that can drift.
 */
export { cn } from "./utils";
