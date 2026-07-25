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
import { Plus, PackageMinus } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

interface StockAdjustmentLine {
  id: string;
  item_id: string;
  quantity_change: string | number;
}

interface StockAdjustment {
  id: string;
  date: string;
  reason: string;
  notes?: string;
  created_at: string;
  items: StockAdjustmentLine[];
}

const reasonLabels: Record<string, string> = {
  initial_balance: "Initial Balance (رصيد افتتاحي)",
  damage: "Damage (تالف)",
  correction: "Correction (تسوية)",
};

const reasonColors: Record<string, string> = {
  initial_balance: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  damage: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  correction: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
};

export default function AdjustmentsPage() {
  const { data: adjustments, isLoading, isError, error } = useQuery<StockAdjustment[]>({
    queryKey: ["inventory", "adjustments"],
    queryFn: () => apiClient.get("/inventory/adjustments"),
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Stock Adjustments (تسويات المخزون)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Track manual stock changes, damages, and initial balances.
          </p>
        </div>
        <Link href="/inventory/adjustments/new">
          <Button className="w-full md:w-auto bg-primary text-primary-foreground shadow-lg hover:shadow-primary/25 transition-all">
            <Plus className="w-4 h-4 mr-2" />
            تسوية جديدة (New Adjustment)
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
            <p className="font-medium">Failed to load adjustments.</p>
            <p className="text-sm opacity-80">{error instanceof Error ? error.message : "Unknown error"}</p>
          </div>
        ) : adjustments?.length === 0 ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center">
            <PackageMinus className="w-12 h-12 mb-4 opacity-20" />
            <p className="font-medium text-lg text-slate-700 dark:text-slate-300">No adjustments found</p>
            <p className="text-sm mt-1">
              Start by creating your first stock adjustment or initial balance.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader className="bg-slate-50/50 dark:bg-slate-800/50">
                <TableRow>
                  <TableHead className="font-semibold">Date</TableHead>
                  <TableHead className="font-semibold">Reason</TableHead>
                  <TableHead className="font-semibold text-center">Items Adjusted</TableHead>
                  <TableHead className="font-semibold">Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {adjustments?.map((adj) => (
                  <TableRow key={adj.id} className="group hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors">
                    <TableCell className="font-medium">
                      {new Date(adj.date).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={reasonColors[adj.reason] || ""}>
                        {reasonLabels[adj.reason] || adj.reason}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center font-medium">
                      {adj.items.length} item(s)
                    </TableCell>
                    <TableCell className="text-slate-500 truncate max-w-[200px]">
                      {adj.notes || "-"}
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
