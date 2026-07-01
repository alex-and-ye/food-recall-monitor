interface EmptyStateProps {
  onCheckAgain: () => void;
}

export default function EmptyState({ onCheckAgain }: EmptyStateProps) {
  return (
    <p className="text-lg text-slate-700 text-center">
      No records available. Please check back tomorrow.
    </p>
  );
}
