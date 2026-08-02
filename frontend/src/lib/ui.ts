/**
 * Shared Tailwind class-name constants for consistent dashboard UI chrome.
 */

/** Card container with border, white background, and light shadow. */
export const cardClassName =
  "rounded-xl border border-slate-300 bg-white shadow-sm";

/** Elevated panel container used on detail pages. */
export const panelClassName =
  "rounded-xl border border-slate-300 bg-white p-6 shadow-xl";

/** Primary page heading typography. */
export const pageTitleClassName =
  "text-2xl font-semibold tracking-tight text-slate-950";

/** Section heading / label typography. */
export const sectionLabelClassName =
  "text-base font-medium text-slate-900";

/** Detail field label typography. */
export const detailLabelClassName = "text-base font-medium text-slate-900";

/** Detail field value typography. */
export const detailValueClassName = "mt-1 text-base text-slate-900";

/** Smaller meta text under detail headings. */
export const detailMetaClassName = "text-sm font-medium text-slate-700";

/** Primary body text. */
export const bodyTextClassName = "text-base text-slate-900";

/** Secondary / supporting body text. */
export const bodySecondaryClassName = "text-base text-slate-700";

/** Muted helper or empty-state text. */
export const mutedTextClassName = "text-sm text-slate-500";

/** Primary (filled emerald) button styles. */
export const primaryButtonClassName =
  "rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40";

/** Secondary (outlined) button styles. */
export const secondaryButtonClassName =
  "rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40";

/** External source link styled as a bordered button. */
export const sourceLinkClassName =
  "mt-2 inline-block rounded-lg border border-slate-900 bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-900 hover:text-white";

/** Back-navigation control styles. */
export const backButtonClassName =
  "mb-6 inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900";

/** Standard text input field styles. */
export const inputClassName =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40";

/** Standard select field styles. */
export const selectClassName =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm transition-colors focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40";

/** Form field label styles. */
export const formLabelClassName = "mb-1.5 block text-base font-medium text-slate-900";
