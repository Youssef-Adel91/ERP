"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

interface Item { id: string; name: string; sku: string; cost: number | string; }
interface Contact { id: string; name: string; name_ar?: string; }

const invoiceLineSchema = z.object({
  item_id: z.string().min(1, "Please select an item."),
  quantity: z.coerce.number().min(1, "Quantity must be at least 1"),
  unit_price: z.coerce.number().min(0, "Price cannot be negative"),
});

const invoiceSchema = z.object({
  supplier_id: z.string().min(1, "Please select a supplier."),
  invoice_date: z.string().min(1, "Date is required"),
  lines: z.array(invoiceLineSchema).min(1, "At least one item is required."),
});

type InvoiceFormValues = z.infer<typeof invoiceSchema>;

export default function NewPurchaseInvoicePage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: items, isLoading: itemsLoading } = useQuery<Item[]>({
    queryKey: ["inventory", "items"],
    queryFn: () => apiClient.get("/inventory/items"),
  });

  const { data: contacts, isLoading: contactsLoading } = useQuery<Contact[]>({
    queryKey: ["contacts"],
    queryFn: () => apiClient.get("/contacts?type=supplier"),
  });

  const form = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceSchema) as any,
    defaultValues: {
      supplier_id: "",
      invoice_date: new Date().toISOString().split("T")[0],
      lines: [{ item_id: "", quantity: 1, unit_price: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ name: "lines", control: form.control });

  const watchedLines = useWatch({ control: form.control, name: "lines" });
  const [grandTotal, setGrandTotal] = useState(0);

  useEffect(() => {
    const total = watchedLines?.reduce((sum, line) => {
      const q = Number(line.quantity) || 0;
      const p = Number(line.unit_price) || 0;
      return sum + (q * p);
    }, 0) || 0;
    setGrandTotal(total);
  }, [watchedLines]);

  const { mutate, isPending } = useMutation({
    mutationFn: (data: InvoiceFormValues) => {
      const payload = { ...data, invoice_date: new Date(data.invoice_date).toISOString() };
      return apiClient.post("/purchases/invoices", payload);
    },
    onSuccess: () => {
      toast.success("Purchase Invoice created successfully!");
      queryClient.invalidateQueries({ queryKey: ["purchases", "invoices"] });
      // Invalidate items because stock increased!
      queryClient.invalidateQueries({ queryKey: ["inventory", "items"] });
      router.push("/purchases/invoices");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to create invoice.");
    },
  });

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex items-center gap-4">
        <Link href="/purchases/invoices">
          <Button variant="outline" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            New Purchase Invoice (فاتورة مشتريات جديدة)
          </h1>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit((d) => mutate(d))} className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Supplier & Details</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField control={form.control} name="supplier_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Supplier (المورد)</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger><SelectValue placeholder={contactsLoading ? "Loading..." : "Select a supplier"} /></SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {contacts?.map(c => (
                          <SelectItem key={c.id} value={c.id}>{c.name_ar || c.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="invoice_date" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Date (التاريخ)</FormLabel>
                    <FormControl><Input type="date" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div><CardTitle>Invoice Lines</CardTitle></div>
              <Button type="button" variant="outline" size="sm" onClick={() => append({ item_id: "", quantity: 1, unit_price: 0 })}>
                <Plus className="h-4 w-4 mr-2" /> Add Row
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {fields.map((field, index) => {
                const q = Number(watchedLines?.[index]?.quantity) || 0;
                const p = Number(watchedLines?.[index]?.unit_price) || 0;
                const lineTotal = (q * p).toFixed(2);

                return (
                  <div key={field.id} className="flex flex-col sm:flex-row gap-4 items-start sm:items-end p-4 border rounded-lg bg-slate-50/50 dark:bg-slate-800/20">
                    <FormField control={form.control} name={`lines.${index}.item_id`} render={({ field: selectField }) => (
                      <FormItem className="flex-1 w-full sm:w-auto">
                        <FormLabel>Item</FormLabel>
                        <Select 
                          onValueChange={(val) => {
                            selectField.onChange(val);
                            // Auto-fill cost if available
                            const selectedItem = (Array.isArray(items) ? items : [])?.find((i: any) => i.id === val);
                            if (selectedItem) {
                              form.setValue(`lines.${index}.unit_price`, Number(selectedItem.cost));
                            }
                          }} 
                          defaultValue={selectField.value}
                        >
                          <FormControl><SelectTrigger><SelectValue placeholder={itemsLoading ? "Loading..." : "Select an item"} /></SelectTrigger></FormControl>
                          <SelectContent>
                            {items?.map(item => (
                              <SelectItem key={item.id} value={item.id}>{item.sku} - {item.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )} />
                    
                    <FormField control={form.control} name={`lines.${index}.quantity`} render={({ field: inputField }) => (
                      <FormItem className="w-full sm:w-32"><FormLabel>Qty</FormLabel><FormControl><Input type="number" step="any" min="1" {...inputField} /></FormControl></FormItem>
                    )} />
                    
                    <FormField control={form.control} name={`lines.${index}.unit_price`} render={({ field: inputField }) => (
                      <FormItem className="w-full sm:w-32"><FormLabel>Unit Price</FormLabel><FormControl><Input type="number" step="any" min="0" {...inputField} /></FormControl></FormItem>
                    )} />

                    <div className="w-full sm:w-32 pb-2">
                      <FormLabel className="text-slate-500">Total</FormLabel>
                      <div className="font-semibold text-lg">{lineTotal}</div>
                    </div>

                    <Button type="button" variant="destructive" size="icon" className="mb-0 sm:mb-1" disabled={fields.length === 1} onClick={() => remove(index)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <div className="flex flex-col md:flex-row justify-between items-center bg-slate-100 dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
            <div className="text-xl text-slate-600 dark:text-slate-400">Grand Total: <span className="text-3xl font-bold text-slate-900 dark:text-white ml-2">{grandTotal.toFixed(2)}</span> EGP</div>
            <div className="flex gap-4 mt-4 md:mt-0">
              <Link href="/purchases/invoices"><Button type="button" variant="ghost">Cancel</Button></Link>
              <Button type="submit" disabled={isPending} className="bg-primary min-w-[150px]">
                {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "Confirm Invoice"}
              </Button>
            </div>
          </div>

        </form>
      </Form>
    </div>
  );
}
