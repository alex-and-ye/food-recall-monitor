import { backButtonClassName } from "@/lib/ui";

interface BackButtonProps {
  onClick: () => void;
  label?: string;
}

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
