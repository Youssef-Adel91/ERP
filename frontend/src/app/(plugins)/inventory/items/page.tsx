"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/lib/api-client";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Plus, PackageOpen } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";

interface Item {
  id: string;
  name: string;
  name_ar?: string;
  sku: string;
  category?: string;
  price: string | number;
  cost: string | number;
  quantity_on_hand: string | number;
  is_active: boolean;
}

export default function ItemsPage() {
  const [searchTerm, setSearchTerm] = useState("");

  const { data: items, isLoading, isError, error } = useQuery<Item[]>({
    queryKey: ["inventory", "items"],
    queryFn: () => apiClient.get("/inventory/items"),
  });

  const filteredItems = items?.filter(
    (item) =>
      item.sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.name_ar && item.name_ar.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Items Catalog (الأصناف)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Manage your wholesale inventory, SKUs, and pricing.
          </p>
        </div>
        <Link href="/inventory/items/new">
          <Button className="w-full md:w-auto bg-primary text-primary-foreground shadow-lg hover:shadow-primary/25 transition-all">
            <Plus className="w-4 h-4 mr-2" />
            إضافة صنف (Add Item)
          </Button>
        </Link>
      </div>

      <div className="flex items-center gap-2 max-w-md">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <Input
            placeholder="Search by SKU or Name..."
            className="pl-9 bg-white dark:bg-slate-900"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border rounded-xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="p-12 text-center text-red-500">
            <p className="font-medium">Failed to load items.</p>
            <p className="text-sm opacity-80">{error instanceof Error ? error.message : "Unknown error"}</p>
          </div>
        ) : filteredItems?.length === 0 ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center">
            <PackageOpen className="w-12 h-12 mb-4 opacity-20" />
            <p className="font-medium text-lg text-slate-700 dark:text-slate-300">No items found</p>
            <p className="text-sm mt-1">
              {searchTerm ? "Try a different search term." : "Start by adding your first item to the catalog."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader className="bg-slate-50/50 dark:bg-slate-800/50">
                <TableRow>
                  <TableHead className="font-semibold">SKU</TableHead>
                  <TableHead className="font-semibold">Name (English)</TableHead>
                  <TableHead className="font-semibold text-right text-slate-500">الاسم (عربي)</TableHead>
                  <TableHead className="font-semibold text-right">Price</TableHead>
                  <TableHead className="font-semibold text-right">Cost</TableHead>
                  <TableHead className="font-semibold text-right">Stock</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems?.map((item) => (
                  <TableRow key={item.id} className="group hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors">
                    <TableCell className="font-mono text-sm font-medium">{item.sku}</TableCell>
                    <TableCell className="font-medium">{item.name}</TableCell>
                    <TableCell className="text-right" dir="rtl">{item.name_ar || "-"}</TableCell>
                    <TableCell className="text-right font-medium text-emerald-600 dark:text-emerald-400">
                      {Number(item.price).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right text-slate-500">
                      {Number(item.cost).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {Number(item.quantity_on_hand)}
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
