"use client";

import { useEffect, useState } from "react";
import {
  getProperties,
  forceRescrape,
  type GetPropertiesFilters,
} from "@/actions/properties";
import type { PropertyListItem } from "@/types";
import { ToastContainer, type ToastMessage } from "@/components/ui/ToastContainer";

export default function PropertiesPage() {
  const [properties, setProperties] = useState<PropertyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [rescrapingIds, setRescrapingIds] = useState<Set<string>>(new Set());
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // Filters
  const [filters, setFilters] = useState<GetPropertiesFilters>({
    limit: 50,
    offset: 0,
  });
  const [searchInput, setSearchInput] = useState("");

  const addToast = (message: string, type: "success" | "error" | "info" = "info", duration = 4000) => {
    const id = `toast-${Date.now()}`;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Load properties when filters change
  useEffect(() => {
    setLoading(true);
    getProperties(filters)
      .then(setProperties)
      .catch((err) => {
        console.error("Failed to load properties:", err);
        addToast("Failed to load properties", "error");
      })
      .finally(() => setLoading(false));
  }, [filters]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined, // Remove filter if empty
      offset: 0, // Reset to first page
    }));
  };

  const handleSearch = () => {
    setFilters((prev) => ({
      ...prev,
      search: searchInput || undefined,
      offset: 0,
    }));
  };

  const handleRescrape = async (property: PropertyListItem) => {
    if (rescrapingIds.has(property.id)) return;

    setRescrapingIds((prev) => new Set(prev).add(property.id));

    try {
      const result = await forceRescrape(property.id);
      addToast(result.message, "success");

      // Refresh properties list
      const updated = await getProperties(filters);
      setProperties(updated);
    } catch (err) {
      console.error("Failed to trigger rescrape:", err);
      addToast("Failed to trigger rescrape", "error");
    } finally {
      setRescrapingIds((prev) => {
        const next = new Set(prev);
        next.delete(property.id);
        return next;
      });
    }
  };

  const getScrapeStatusBadge = (status: PropertyListItem["scrape_status"]) => {
    const badgeClasses: Record<string, string> = {
      NEVER_SCRAPED: "bg-gray-600 text-gray-100",
      UP_TO_DATE: "bg-green-600 text-green-100",
      NEEDS_REFRESH: "bg-yellow-600 text-yellow-100",
      FAILED: "bg-red-600 text-red-100",
    };

    return (
      <span
        className={`px-2 py-1 rounded text-xs font-medium ${badgeClasses[status]}`}
      >
        {status.replace(/_/g, " ")}
      </span>
    );
  };

  const getReportStatusBadge = (status: string | null) => {
    if (!status) return <span className="text-gray-500 text-sm">No report</span>;

    const badgeClasses: Record<string, string> = {
      QUEUING: "bg-gray-600 text-gray-100",
      PROCESSING: "bg-blue-600 text-blue-100",
      READY: "bg-green-600 text-green-100",
      FAILED: "bg-red-600 text-red-100",
    };

    return (
      <span
        className={`px-2 py-1 rounded text-xs font-medium ${
          badgeClasses[status] || "bg-gray-600 text-gray-100"
        }`}
      >
        {status}
      </span>
    );
  };

  const getConfidenceBadge = (confidence: "HIGH" | "MEDIUM" | "LOW" | null) => {
    if (!confidence) return <span className="text-gray-500 text-sm">—</span>;

    const badgeClasses: Record<string, string> = {
      HIGH: "bg-green-600 text-green-100",
      MEDIUM: "bg-yellow-600 text-yellow-100",
      LOW: "bg-red-600 text-red-100",
    };

    return (
      <span
        className={`px-2 py-1 rounded text-xs font-medium ${badgeClasses[confidence]}`}
      >
        {confidence}
      </span>
    );
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-white">Properties Browser</h1>
        <div className="text-gray-400">
          Showing {properties.length} properties
        </div>
      </div>

      {/* Filters */}
      <div className="bg-gray-800 p-4 rounded-lg space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* State Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              State
            </label>
            <select
              className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              value={filters.state || ""}
              onChange={(e) => handleFilterChange("state", e.target.value)}
            >
              <option value="">All States</option>
              <option value="NSW">NSW</option>
              <option value="VIC">VIC</option>
              <option value="QLD">QLD</option>
              <option value="SA">SA</option>
              <option value="WA">WA</option>
              <option value="TAS">TAS</option>
              <option value="NT">NT</option>
              <option value="ACT">ACT</option>
            </select>
          </div>

          {/* Report Status Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Report Status
            </label>
            <select
              className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              value={filters.status || ""}
              onChange={(e) => handleFilterChange("status", e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="QUEUING">Queuing</option>
              <option value="PROCESSING">Processing</option>
              <option value="READY">Ready</option>
              <option value="FAILED">Failed</option>
            </select>
          </div>

          {/* Limit */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Results per page
            </label>
            <select
              className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              value={filters.limit || 50}
              onChange={(e) =>
                handleFilterChange("limit", e.target.value)
              }
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
            </select>
          </div>
        </div>

        {/* Search Bar */}
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search by address..."
            className="flex-1 bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
          {filters.search && (
            <button
              onClick={() => {
                setSearchInput("");
                handleFilterChange("search", "");
              }}
              className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Properties Table */}
      <div className="bg-gray-800 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">
            Loading properties...
          </div>
        ) : properties.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            No properties found. Try adjusting your filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-900 border-b border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Address
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    State
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    LGA
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Scrape Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Report Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Confidence
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Last Scraped
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {properties.map((property) => (
                  <tr
                    key={property.id}
                    className="hover:bg-gray-750 transition-colors"
                  >
                    <td className="px-4 py-3 text-sm text-white max-w-xs">
                      <a
                        href={`/properties/${property.id}`}
                        className="text-blue-400 hover:text-blue-300 hover:underline truncate block"
                      >
                        {property.address_string}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-300">
                      {property.state}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-300">
                      {property.lga_name || "—"}
                    </td>
                    <td className="px-4 py-3">
                      {getScrapeStatusBadge(property.scrape_status)}
                    </td>
                    <td className="px-4 py-3">
                      {getReportStatusBadge(property.report_status)}
                    </td>
                    <td className="px-4 py-3">
                      {getConfidenceBadge(property.overall_confidence)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-300">
                      {property.last_scraped_at
                        ? new Date(property.last_scraped_at).toLocaleDateString()
                        : "Never"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleRescrape(property)}
                          disabled={rescrapingIds.has(property.id)}
                          className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors disabled:bg-gray-600 disabled:cursor-not-allowed"
                        >
                          {rescrapingIds.has(property.id)
                            ? "Queueing..."
                            : "Re-scrape"}
                        </button>
                        <a
                          href={`/properties/${property.id}`}
                          className="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 transition-colors"
                        >
                          View Details
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {!loading && properties.length > 0 && (
        <div className="flex justify-between items-center">
          <button
            onClick={() =>
              setFilters((prev) => ({
                ...prev,
                offset: Math.max(0, (prev.offset || 0) - (prev.limit || 50)),
              }))
            }
            disabled={(filters.offset || 0) === 0}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors disabled:bg-gray-800 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <div className="text-gray-400">
            Page {Math.floor((filters.offset || 0) / (filters.limit || 50)) + 1}
          </div>
          <button
            onClick={() =>
              setFilters((prev) => ({
                ...prev,
                offset: (prev.offset || 0) + (prev.limit || 50),
              }))
            }
            disabled={properties.length < (filters.limit || 50)}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors disabled:bg-gray-800 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
      
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
