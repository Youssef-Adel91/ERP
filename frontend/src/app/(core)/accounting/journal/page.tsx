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
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface TransactionLine {
  id: string;
  account_code: string;
  account_name: string;
  debit: string | number;
  credit: string | number;
}

interface JournalEntry {
  id: string;
  reference: string;
  description: string;
  status: string;
  source_type: string;
  created_at: string;
  lines: TransactionLine[];
}

export default function JournalEntriesPage() {
  const { data: entries, isLoading, isError } = useQuery<JournalEntry[]>({
    queryKey: ["accounting", "journal-entries"],
    queryFn: () => apiClient.get("/accounting/journal-entries"),
  });

  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (id: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedRows(newExpanded);
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <BookOpen className="w-8 h-8 text-primary" />
          Journal Entries (قيود اليومية)
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          The core double-entry accounting ledger tracking all financial movements.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Accounting Ledger</CardTitle>
          <CardDescription>All auto-generated and manual journal entries.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="p-12 text-center text-red-500">Failed to load journal entries.</div>
          ) : entries?.length === 0 ? (
            <div className="p-16 text-center text-slate-500">No journal entries found.</div>
          ) : (
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader className="bg-slate-50 dark:bg-slate-900">
                  <TableRow>
                    <TableHead className="w-10"></TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Reference</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries?.map((entry) => (
                    <React.Fragment key={entry.id}>
                      <TableRow 
                        className="cursor-pointer hover:bg-slate-50/50 dark:hover:bg-slate-800/50"
                        onClick={() => toggleRow(entry.id)}
                      >
                        <TableCell>
                          {expandedRows.has(entry.id) ? (
                            <ChevronDown className="w-4 h-4 text-slate-500" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-slate-500" />
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">{new Date(entry.created_at).toLocaleString()}</TableCell>
                        <TableCell className="font-semibold">{entry.reference}</TableCell>
                        <TableCell className="text-slate-600 dark:text-slate-300">{entry.description}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="capitalize text-slate-500">
                            {entry.source_type || 'manual'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge variant={entry.status === 'posted' ? 'default' : 'secondary'} className={
                            entry.status === 'posted' ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-100' : ''
                          }>
                            {entry.status.toUpperCase()}
                          </Badge>
                        </TableCell>
                      </TableRow>
                      
                      {/* Expanded Sub-Table for Lines */}
                      {expandedRows.has(entry.id) && (
                        <TableRow className="bg-slate-50/30 dark:bg-slate-900/30 hover:bg-slate-50/30">
                          <TableCell colSpan={6} className="p-0 border-b">
                            <div className="p-6">
                              <Table className="bg-white dark:bg-slate-950 border rounded-lg shadow-sm">
                                <TableHeader className="bg-slate-100/50 dark:bg-slate-900">
                                  <TableRow>
                                    <TableHead>Account</TableHead>
                                    <TableHead className="text-right text-emerald-700 font-semibold">Debit (مدين)</TableHead>
                                    <TableHead className="text-right text-red-700 font-semibold">Credit (دائن)</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {entry.lines.map((line) => {
                                    const isDebit = Number(line.debit) > 0;
                                    const isCredit = Number(line.credit) > 0;
                                    return (
                                      <TableRow key={line.id}>
                                        <TableCell>
                                          <span className="font-mono text-slate-500 mr-2">{line.account_code}</span>
                                          <span className="font-medium">{line.account_name}</span>
                                        </TableCell>
                                        <TableCell className="text-right font-mono font-medium text-emerald-600">
                                          {isDebit ? Number(line.debit).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}
                                        </TableCell>
                                        <TableCell className="text-right font-mono font-medium text-red-600">
                                          {isCredit ? Number(line.credit).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}
                                        </TableCell>
                                      </TableRow>
                                    );
                                  })}
                                  {/* Totals Footer row */}
                                  <TableRow className="bg-slate-50 font-bold border-t-2">
                                    <TableCell className="text-right uppercase text-xs tracking-wider">Totals</TableCell>
                                    <TableCell className="text-right font-mono text-emerald-700">
                                      {entry.lines.reduce((sum, l) => sum + Number(l.debit), 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                    </TableCell>
                                    <TableCell className="text-right font-mono text-red-700">
                                      {entry.lines.reduce((sum, l) => sum + Number(l.credit), 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                    </TableCell>
                                  </TableRow>
                                </TableBody>
                              </Table>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
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
