export function LaterPhase({ title, description }: { title: string; description: string }) {
  return (
    <section className="surface-card max-w-xl rounded-lg border border-line p-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-3 text-muted">{description}</p>
    </section>
  );
}
