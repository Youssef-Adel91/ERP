import { CoreLayout } from "@/components/layout/CoreLayout";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <CoreLayout>{children}</CoreLayout>;
}
