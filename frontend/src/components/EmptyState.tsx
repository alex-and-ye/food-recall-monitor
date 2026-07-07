import { bodySecondaryClassName, cardClassName } from "@/lib/ui";

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
