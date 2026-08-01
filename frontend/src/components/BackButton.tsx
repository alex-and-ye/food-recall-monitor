/**
 * Back-navigation control used on detail pages.
 */

import { backButtonClassName } from "@/lib/ui";

/** Props for the back button component. */
interface BackButtonProps {
  onClick: () => void;
  label?: string;
}

/**
 * Renders a left-chevron icon for the back button.
 *
 * @returns SVG icon element.
 */
function ChevronLeftIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

/**
 * Renders a text button that navigates back (typically via `router.back()`).
 *
 * @param props.onClick - Click handler for navigation.
 * @param props.label - Optional button label (defaults to `"Back"`).
 * @returns Back button element.
 */
export default function BackButton({
  onClick,
  label = "Back",
}: BackButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={backButtonClassName}
    >
      <ChevronLeftIcon />
      {label}
    </button>
  );
}
