export function TabButton({ active, onClick, label, subtitle }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all mr-1 ${
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:text-card-foreground hover:bg-muted/50"
      }`}
    >
      {label}
      {subtitle && (
        <span className={`ml-1.5 text-[10px] ${
          active ? "text-accent-foreground/60" : "text-muted-foreground/60"
        }`}>
          {subtitle}
        </span>
      )}
    </button>
  );
}