import type {ReactNode} from "react";

import {Card} from "@/components/ui/card";
import {Table, TableBody, TableCell, TableHead, TableHeader, TableRow} from "@/components/ui/table";

export type DataColumn = {
    label: ReactNode;
    className?: string;
};

type Label = {"aria-labelledby": string} | {"aria-label": string};

/** A list in a card: the column headers, then `children` (the rows), or one
 * row saying `loadingText` while `loading`. A falsy column is left out, for
 * columns only some users see. */
export function DataTable({
    columns,
    loading = false,
    loadingText,
    children,
    ...label
}: Label & {
    columns: (DataColumn | false | null)[];
    loading?: boolean;
    loadingText?: string;
    children: ReactNode;
}) {
    const shown = columns.filter((column): column is DataColumn => Boolean(column));
    return (
        <Card className="gap-0 py-0">
            <Table {...label}>
                <TableHeader>
                    <TableRow className="hover:bg-transparent">
                        {shown.map((column, index) => (
                            <TableHead key={index} className={column.className}>
                                {column.label}
                            </TableHead>
                        ))}
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {loading ? (
                        <TableRow className="hover:bg-transparent">
                            <TableCell colSpan={shown.length} className="px-4 py-8 text-muted-foreground">
                                {loadingText}
                            </TableCell>
                        </TableRow>
                    ) : (
                        children
                    )}
                </TableBody>
            </Table>
        </Card>
    );
}
