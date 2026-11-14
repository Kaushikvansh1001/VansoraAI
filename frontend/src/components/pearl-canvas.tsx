export function PearlCanvas({ children }: { children: React.ReactNode }) {
  return (
    <div className="pearl-canvas">
      <div className="pearl-grain" aria-hidden="true" />
      <div className="relative z-[1] min-h-screen">{children}</div>
    </div>
  );
}
