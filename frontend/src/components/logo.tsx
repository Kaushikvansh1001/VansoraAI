export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" className="fill-ink" />
      <path d="M8 7.5h4.1L16 18.2 19.9 7.5H24L16.9 24h-1.8L8 7.5z" className="fill-pearl" />
    </svg>
  );
}
