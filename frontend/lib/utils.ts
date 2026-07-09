import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combines multiple Tailwind CSS classes using clsx and merges duplicates using tailwind-merge.
 *
 * @param inputs - Array of class values to combine and merge.
 * @returns The merged CSS class name string.
 */
export function cn(...inputs: ClassValue[]): string { 
  return twMerge(clsx(inputs)); 
}

/**
 * Formats an ISO 8601 date string to the es-ES locale format with short date and time styles.
 *
 * @param iso - Optional ISO date string.
 * @returns Formatted date string, or "—" if the date is undefined or empty.
 */
export function fmtDate(iso?: string): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

/**
 * Formats an ISO date string into a human-readable relative time string (e.g. "hace 5s", "hace 3m", "hace 2h").
 * Falls back to es-ES locale formatting for differences greater than 24 hours.
 *
 * @param iso - Optional ISO date string.
 * @returns Relative time string, or "—" if the date is undefined or empty.
 */
export function fmtRelative(iso?: string): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `hace ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  return fmtDate(iso);
}

/**
 * Label mapping dictionary for hardware types.
 */
export const HW_LABELS: Record<string, string> = {};

/**
 * Text color CSS class mappings for target resource statuses.
 */
export const STATUS_COLORS: Record<string, string> = {
  online: "text-aura-success",
  offline: "text-aura-dim",
  running: "text-aura-accent",
  compiling: "text-aura-warning",
  failed: "text-aura-danger",
  pending: "text-aura-dim",
  sent: "text-aura-info",
  ready: "text-aura-success",
};
