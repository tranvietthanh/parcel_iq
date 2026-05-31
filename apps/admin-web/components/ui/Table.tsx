import type { ReactNode } from "react";

type TableProps = {
  children: ReactNode;
};

export function Table({ children }: TableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-700">{children}</table>
    </div>
  );
}

type TableHeadProps = {
  children: ReactNode;
};

export function TableHead({ children }: TableHeadProps) {
  return (
    <thead className="bg-gray-800">
      <tr>{children}</tr>
    </thead>
  );
}

type TableHeaderProps = {
  children: ReactNode;
};

export function TableHeader({ children }: TableHeaderProps) {
  return (
    <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
      {children}
    </th>
  );
}

type TableBodyProps = {
  children: ReactNode;
};

export function TableBody({ children }: TableBodyProps) {
  return <tbody className="bg-gray-900 divide-y divide-gray-700">{children}</tbody>;
}

type TableRowProps = {
  children: ReactNode;
};

export function TableRow({ children }: TableRowProps) {
  return <tr className="hover:bg-gray-800">{children}</tr>;
}

type TableCellProps = {
  children: ReactNode;
  className?: string;
};

export function TableCell({ children, className = "" }: TableCellProps) {
  return <td className={`px-6 py-4 whitespace-nowrap text-sm text-gray-300 ${className}`}>{children}</td>;
}
