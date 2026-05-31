"use client";

import { useState, useEffect } from "react";
import { getDataSources, testDataSource } from "@/actions/sources";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  Table,
  TableHead,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/Table";
import type { DataSource } from "@/types";
import { formatDate } from "@/lib/format";

export default function SourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDataSources().then((data) => {
      setSources(data);
      setLoading(false);
    });
  }, []);

  const handleTest = async (id: string) => {
    try {
      const result = await testDataSource(id);
      alert(result.success ? "✓ Connection successful" : `✗ ${result.message}`);
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Data Sources</h2>
        <p className="mt-1 text-sm text-gray-500">
          Manage scraper adapter configurations
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-medium text-gray-900">
              {loading ? "Loading..." : `${sources.length} Sources`}
            </h3>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHead>
              <TableHeader>LGA</TableHeader>
              <TableHeader>Adapter</TableHeader>
              <TableHeader>Base URL</TableHeader>
              <TableHeader>Last Scraped</TableHeader>
              <TableHeader>Status</TableHeader>
              <TableHeader>Actions</TableHeader>
            </TableHead>
            <TableBody>
              {sources.map((source) => (
                <TableRow key={source.id}>
                  <TableCell>
                    {source.lga_name} ({source.lga_code})
                  </TableCell>
                  <TableCell>{source.adapter_name}</TableCell>
                  <TableCell className="max-w-xs truncate">
                    {source.base_url}
                  </TableCell>
                  <TableCell>{formatDate(source.last_scraped_at)}</TableCell>
                  <TableCell>
                    <Badge color={source.is_active ? "green" : "gray"}>
                      {source.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="secondary"
                      onClick={() => handleTest(source.id)}
                    >
                      Test
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
