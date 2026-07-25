"use client";

import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Trash2, Plus, Receipt } from "lucide-react";
import { toast } from "sonner";
import { useWatch } from "react-hook-form";
import { useMemo } from "react";

const lineSchema = z.object({
  item_id: z.string().min(1, "Item is required"),
  quantity: z.coerce.number().min(0.0001, "Quantity must be greater than 0"),
  unit_price: z.coerce.number().min(0, "Price cannot be negative"),
});

const formSchema = z.object({
  customer_id: z.string().min(1, "Customer is required"),
  lines: z.array(lineSchema).min(1, "At least one item is required"),
});

type FormValues = z.infer<typeof formSchema>;

export default function NewSalesInvoicePage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: contacts } = useQuery({
    queryKey: ["contacts"],
    queryFn: () => apiClient.get("/contacts?type=customer"),
  });

  const { data: items } = useQuery({
    queryKey: ["inventory", "items"],
    queryFn: () => apiClient.get("/inventory/items"),
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      customer_id: "",
      lines: [{ item_id: "", quantity: 1, unit_price: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "lines",
  });

  const createMutation = useMutation({
    mutationFn: (data: FormValues) => apiClient.post("/sales/invoices", data),
    onSuccess: () => {
      toast.success("Sales Invoice created successfully");
      queryClient.invalidateQueries({ queryKey: ["sales_invoices"] });
      router.push("/sales/invoices");
    },
    onError: (error: any) => {
      toast.error(
        "Error creating invoice", {
        description: error?.response?.data?.detail || "An unexpected error occurred",
      });
    },
  });

  // Dynamically calculate totals
  const watchLines = useWatch({ control: form.control, name: "lines" });
  const grandTotal = useMemo(() => {
    return watchLines.reduce((sum, line) => {
      const q = Number(line.quantity) || 0;
      const p = Number(line.unit_price) || 0;
      return sum + q * p;
    }, 0);
  }, [watchLines]);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center gap-3">
        <Receipt className="w-8 h-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">New Sales Invoice</h1>
          <p className="text-slate-500">Record a sale and deduct inventory stock.</p>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit((d) => createMutation.mutate(d))} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Customer Details</CardTitle>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="customer_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Customer</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a customer" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Array.isArray(contacts) && contacts.map((c: any) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.name} ({c.contact_type})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Line Items</CardTitle>
                <CardDescription>Select items to sell.</CardDescription>
              </div>
              <Button type="button" variant="outline" onClick={() => append({ item_id: "", quantity: 1, unit_price: 0 })}>
                <Plus className="w-4 h-4 mr-2" /> Add Item
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {fields.map((field, index) => {
                const currentItemId = watchLines[index]?.item_id;
                const currentItem = (Array.isArray(items) ? items : [])?.find((i: any) => i.id === currentItemId);

                return (
                  <div key={field.id} className="flex gap-4 items-start p-4 border rounded-lg bg-slate-50/50 dark:bg-slate-900/50">
                    <FormField
                      control={form.control}
                      name={`lines.${index}.item_id`}
                      render={({ field: selectField }) => (
                        <FormItem className="flex-[2]">
                          <FormLabel>Item</FormLabel>
                          <Select
                            onValueChange={(val) => {
                              selectField.onChange(val);
                              // Auto-fill price
                              const selectedItem = (Array.isArray(items) ? items : [])?.find((i: any) => i.id === val);
                              if (selectedItem) {
                                form.setValue(`lines.${index}.unit_price`, selectedItem.price);
                              }
                            }}
                            defaultValue={selectField.value}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select item" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {Array.isArray(items) && items.map((itm: any) => (
                                <SelectItem key={itm.id} value={itm.id} disabled={itm.quantity_on_hand <= 0}>
                                  {itm.name} (SKU: {itm.sku}) - Avail: {itm.quantity_on_hand}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name={`lines.${index}.quantity`}
                      render={({ field: inputField }) => (
                        <FormItem className="flex-1">
                          <FormLabel>Quantity</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              step="1"
                              {...inputField}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value);
                                inputField.onChange(val);
                                // Validation hint logic if we want to add realtime max constraint check
                              }}
                            />
                          </FormControl>
                          {currentItem && currentItem.quantity_on_hand < watchLines[index].quantity && (
                             <p className="text-[0.8rem] text-red-500 font-medium">Exceeds stock ({currentItem.quantity_on_hand})</p>
                          )}
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name={`lines.${index}.unit_price`}
                      render={({ field: inputField }) => (
                        <FormItem className="flex-1">
                          <FormLabel>Unit Price</FormLabel>
                          <FormControl>
                            <Input type="number" step="0.01" {...inputField} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="flex-1 pt-8 text-right font-mono font-bold text-slate-700 dark:text-slate-200">
                      {(
                        (Number(watchLines[index]?.quantity) || 0) *
                        (Number(watchLines[index]?.unit_price) || 0)
                      ).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>

                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="mt-8 text-red-500 hover:text-red-700 hover:bg-red-50"
                      onClick={() => remove(index)}
                      disabled={fields.length === 1}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                );
              })}
              
              <div className="flex justify-end p-4 text-xl">
                <span className="font-semibold mr-4">Grand Total:</span>
                <span className="font-mono font-bold text-primary">{grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-4">
            <Button type="button" variant="outline" onClick={() => router.back()} disabled={createMutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Confirming..." : "Confirm Invoice"}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
