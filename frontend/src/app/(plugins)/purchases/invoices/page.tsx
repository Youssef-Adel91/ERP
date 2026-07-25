"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Plus, ReceiptText } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

interface PurchaseInvoice {
  id: string;
  supplier_id: string;
  invoice_date: string;
  total_amount: string | number;
  status: string;
  created_at: string;
}

interface Contact {
  id: string;
  name: string;
  name_ar?: string;
}

export default function PurchaseInvoicesPage() {
  const { data: invoices, isLoading, isError, error } = useQuery<PurchaseInvoice[]>({
    queryKey: ["purchases", "invoices"],
    queryFn: () => apiClient.get("/purchases/invoices"),
  });

  const { data: contacts } = useQuery<Contact[]>({
    queryKey: ["contacts"],
    queryFn: () => apiClient.get("/contacts?type=supplier"),
  });

  const supplierMap = new Map(contacts?.map(c => [c.id, c.name_ar || c.name]));

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Purchase Invoices (فواتير المشتريات)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Manage your incoming stock and supplier invoices.
          </p>
        </div>
        <Link href="/purchases/invoices/new">
          <Button className="w-full md:w-auto bg-primary text-primary-foreground shadow-lg hover:shadow-primary/25 transition-all">
            <Plus className="w-4 h-4 mr-2" />
            فاتورة مشتريات جديدة (New Purchase Invoice)
          </Button>
        </Link>
      </div>

      <div className="bg-white dark:bg-slate-900 border rounded-xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="p-12 text-center text-red-500">
            <p className="font-medium">Failed to load invoices.</p>
            <p className="text-sm opacity-80">{error instanceof Error ? error.message : "Unknown error"}</p>
          </div>
        ) : invoices?.length === 0 ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center">
            <ReceiptText className="w-12 h-12 mb-4 opacity-20" />
            <p className="font-medium text-lg text-slate-700 dark:text-slate-300">No purchase invoices found</p>
            <p className="text-sm mt-1">
              Start by recording your first supplier invoice.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader className="bg-slate-50/50 dark:bg-slate-800/50">
                <TableRow>
                  <TableHead className="font-semibold">Date</TableHead>
                  <TableHead className="font-semibold">Supplier</TableHead>
                  <TableHead className="font-semibold text-right">Total Amount</TableHead>
                  <TableHead className="font-semibold text-center">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices?.map((inv) => (
                  <TableRow key={inv.id} className="group hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors">
                    <TableCell className="font-medium">
                      {new Date(inv.invoice_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      {supplierMap.get(inv.supplier_id) || inv.supplier_id}
                    </TableCell>
                    <TableCell className="text-right font-medium text-emerald-600 dark:text-emerald-400">
                      {Number(inv.total_amount).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
                        {inv.status.toUpperCase()}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
