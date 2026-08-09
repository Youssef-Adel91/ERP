export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Each auth page (login, register) manages its own full-page layout
  // to match the Stitch direction_6 design exactly.
  return <>{children}</>;
}
