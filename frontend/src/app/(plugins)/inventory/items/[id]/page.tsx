"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useParams } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Package, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

interface Item {
  id: string;
  name: string;
  name_ar?: string;
  sku: string;
  quantity_on_hand: number;
}

interface LedgerEntry {
  date: string;
  transaction_type: string;
  reference: string;
  quantity_change: number;
  running_balance: number;
}

export default function ItemLedgerPage() {
  const { id } = useParams() as { id: string };

  const { data: item, isLoading: itemLoading } = useQuery<Item>({
    queryKey: ["inventory", "items", id],
    queryFn: () => apiClient.get(`/inventory/items/${id}`),
  });

  const { data: ledger, isLoading: ledgerLoading } = useQuery<LedgerEntry[]>({
    queryKey: ["inventory", "items", id, "ledger"],
    queryFn: () => apiClient.get(`/inventory/items/${id}/ledger`),
  });

  if (itemLoading) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!item) {
    return (
      <div className="p-16 text-center text-red-500">
        Item not found.
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex items-center gap-4">
        <Link href="/inventory/items">
          <Button variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Item Stock Ledger (كارت الصنف)
          </h1>
        </div>
      </div>

      {/* Summary Card */}
      <Card className="bg-gradient-to-r from-slate-50 to-white dark:from-slate-900 dark:to-slate-800 shadow-sm border-slate-200 dark:border-slate-800">
        <CardContent className="p-6 flex flex-col sm:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-6">
            <div className="p-4 bg-primary/10 rounded-xl text-primary">
              <Package className="w-10 h-10" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
                {item.name_ar || item.name}
              </h2>
              <p className="text-slate-500 dark:text-slate-400 mt-1">
                SKU: <span className="font-mono text-slate-700 dark:text-slate-300">{item.sku}</span>
              </p>
            </div>
          </div>
          
          <div className="text-center sm:text-right bg-white dark:bg-slate-950 p-4 rounded-xl border border-slate-100 dark:border-slate-800 shadow-sm min-w-[200px]">
            <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">
              Current Stock (الرصيد الحالي)
            </p>
            <div className={`text-4xl font-bold mt-1 ${
              item.quantity_on_hand > 0 ? "text-emerald-600 dark:text-emerald-400" :
              item.quantity_on_hand < 0 ? "text-red-600 dark:text-red-400" :
              "text-slate-400"
            }`}>
              {Number(item.quantity_on_hand).toLocaleString()}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Ledger Table */}
      <Card>
        <CardHeader>
          <CardTitle>Stock Movements (حركة المخزون)</CardTitle>
          <CardDescription>
            Chronological history of all stock transactions for this item.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {ledgerLoading ? (
            <div className="space-y-4">
              {[1,2,3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : ledger?.length === 0 ? (
            <div className="text-center p-8 text-slate-500">
              No stock movements recorded yet.
            </div>
          ) : (
            <div className="overflow-x-auto border rounded-lg">
              <Table>
                <TableHeader className="bg-slate-50 dark:bg-slate-900">
                  <TableRow>
                    <TableHead className="font-semibold whitespace-nowrap">Date (التاريخ)</TableHead>
                    <TableHead className="font-semibold">Type (نوع الحركة)</TableHead>
                    <TableHead className="font-semibold">Reference (المرجع)</TableHead>
                    <TableHead className="font-semibold text-center whitespace-nowrap">Qty Change (التغيير)</TableHead>
                    <TableHead className="font-semibold text-right whitespace-nowrap">Running Balance (الرصيد)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledger?.map((entry, idx) => {
                    const isPositive = entry.quantity_change > 0;
                    const isNegative = entry.quantity_change < 0;
                    
                    return (
                      <TableRow key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                        <TableCell className="whitespace-nowrap text-slate-600 dark:text-slate-300">
                          {new Date(entry.date).toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={`
                            ${entry.transaction_type === 'تسوية مخزنية' ? 'border-blue-200 bg-blue-50 text-blue-700' : ''}
                            ${entry.transaction_type === 'فاتورة مشتريات' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : ''}
                          `}>
                            {entry.transaction_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-slate-500">
                          {entry.reference}
                        </TableCell>
                        <TableCell className="text-center font-mono">
                          <span className={`px-2 py-1 rounded font-bold ${
                            isPositive ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950 dark:text-emerald-400' : 
                            isNegative ? 'text-red-600 bg-red-50 dark:bg-red-950 dark:text-red-400' : 
                            'text-slate-500'
                          }`}>
                            {isPositive ? '+' : ''}{Number(entry.quantity_change).toLocaleString()}
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono font-bold text-lg text-slate-700 dark:text-slate-200">
                          {Number(entry.running_balance).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
