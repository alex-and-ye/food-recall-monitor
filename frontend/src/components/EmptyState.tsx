/**
 * Empty-state placeholder shown when no records are available to display.
 */

import { bodySecondaryClassName, cardClassName } from "@/lib/ui";

/**
 * Renders a centered card informing the user that no records are available.
 *
 * @returns Empty-state UI element.
 */
export default function EmptyState() {
  return (
    <div
      className={`${cardClassName} px-6 py-12 text-center`}
    >
      <p className={`font-medium ${bodySecondaryClassName}`}>
        No records available. Please check back tomorrow.
      </p>
    </div>
  );
}
