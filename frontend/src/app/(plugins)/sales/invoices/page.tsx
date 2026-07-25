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
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { FileText, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface SalesInvoice {
  id: string;
  reference: string;
  customer_id: string;
  invoice_date: string;
  total_amount: number;
  status: string;
  created_at: string;
}

export default function SalesInvoicesPage() {
  const { data: invoices, isLoading, isError } = useQuery<SalesInvoice[]>({
    queryKey: ["sales", "invoices"],
    queryFn: () => apiClient.get("/sales/invoices"),
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <FileText className="w-8 h-8 text-primary" />
            Sales Invoices (فواتير المبيعات)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Manage your outgoing sales and customer billing.
          </p>
        </div>
        <Link href="/sales/invoices/new">
          <Button>
            <Plus className="mr-2 w-4 h-4" /> New Invoice
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Invoices</CardTitle>
          <CardDescription>A chronological list of all confirmed sales.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="p-12 text-center text-red-500">Failed to load sales invoices.</div>
          ) : invoices?.length === 0 ? (
            <div className="p-16 text-center text-slate-500">No sales invoices found. Create one to get started.</div>
          ) : (
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader className="bg-slate-50 dark:bg-slate-900">
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Customer ID</TableHead>
                    <TableHead className="text-right">Total Amount</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices?.map((invoice) => (
                    <TableRow key={invoice.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                      <TableCell className="whitespace-nowrap">{new Date(invoice.invoice_date).toLocaleDateString()}</TableCell>
                      <TableCell className="font-mono text-xs">{invoice.customer_id}</TableCell>
                      <TableCell className="text-right font-mono font-bold text-slate-700 dark:text-slate-200">
                        {Number(invoice.total_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant="default" className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                          {invoice.status.toUpperCase()}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
