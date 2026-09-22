interface EmptyStateProps {
  icon?: string;
  title?: string;
  message: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({
  icon = '♪',
  title = 'Nothing here yet',
  message,
  action,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      <div className="empty-message">{message}</div>
      {action && (
        <button className="btn primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
