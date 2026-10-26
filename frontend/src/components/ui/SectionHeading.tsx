interface SectionHeadingProps {
  title: string;
  count: number;
}

export function SectionHeading({ title, count }: SectionHeadingProps) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      <span className="count-pill">{count}</span>
    </div>
  );
}
