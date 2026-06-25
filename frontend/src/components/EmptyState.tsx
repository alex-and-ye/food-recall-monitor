interface EmptyStateProps {
  onCheckAgain: () => void;
}

export default function EmptyState({ onCheckAgain }: EmptyStateProps) {
  return (
    <p className="text-lg text-slate-700 text-center">
      No records available today. Please check back tomorrow.
    </p>
  );
}
