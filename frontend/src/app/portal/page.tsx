"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getPortalToken } from "@/lib/portal-api-client";

/** Bare /portal hit — send the customer to the right place based on session state. */
export default function PortalIndexPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getPortalToken() ? "/portal/invoices" : "/portal/login");
  }, [router]);

  return null;
}
