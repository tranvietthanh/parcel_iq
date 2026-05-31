"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getPropertyDetail,
  getPropertyReportById,
  getPropertyReports,
  getPropertyReportPdf,
  deletePropertyReportPdf,
  deletePropertyReport,
  forceRescrape,
  forceAiValidate,
} from "@/actions/properties";
import type {
  PropertyDetail,
  PropertyReportFull,
  PropertyReportListItem,
} from "@/types";
import { ToastContainer, type ToastMessage } from "@/components/ui/ToastContainer";
import { JsonViewer } from "@/components/ui/JsonViewer";

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const propertyId = params.id as string;

  const [property, setProperty] = useState<PropertyDetail | null>(null);
  const [reportMeta, setReportMeta] = useState<PropertyReportListItem | null>(null);
  const [report, setReport] = useState<PropertyReportFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [isRawExpanded, setIsRawExpanded] = useState(false);
  const [isLlmExpanded, setIsLlmExpanded] = useState(false);
  const [deletingReportId, setDeletingReportId] = useState<string | null>(null);
  const [deletingPdfReportId, setDeletingPdfReportId] = useState<string | null>(null);
  const [viewingPdfKey, setViewingPdfKey] = useState<string | null>(null);
  const [pendingDeleteReport, setPendingDeleteReport] =
    useState<PropertyReportListItem | null>(null);
  const [rescrapingInProgress, setRescrapingInProgress] = useState(false);
  const [aiValidateInProgress, setAiValidateInProgress] = useState(false);
  const [refreshingInProgress, setRefreshingInProgress] = useState(false);
const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (
    message: string,
    type: "success" | "error" | "info" = "info",
    duration = 4000
  ) => {
    const id = `toast-${Date.now()}`;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Load property details
  useEffect(() => {
    setLoading(true);
    getPropertyDetail(propertyId)
      .then(setProperty)
      .catch((err) => {
        console.error("Failed to load property:", err);
        addToast("Failed to load property details", "error");
      })
      .finally(() => setLoading(false));
  }, [propertyId]);

  // Load all reports for this property
  useEffect(() => {
    getPropertyReports(propertyId)
      .then((items) => {
        setReportMeta(items[0] ?? null);
      })
      .catch((err) => {
        console.error("Failed to load property report metadata:", err);
        addToast("Failed to load property report metadata", "error");
      });
  }, [propertyId]);

  // Load report when report metadata changes
  useEffect(() => {
    if (!reportMeta) {
      setReport(null);
      return;
    }

    setReport(null);
    setLoadingReport(true);
    getPropertyReportById(propertyId, reportMeta.id, "full")
      .then(setReport)
      .catch((err) => {
        console.error("Failed to load report:", err);
        // Don't show error if report doesn't exist yet
        if (!err.message?.includes("404")) {
          addToast("Failed to load report", "error");
        }
        setReport(null);
      })
      .finally(() => setLoadingReport(false));
  }, [propertyId, reportMeta]);

  // JSON panels start collapsed whenever context changes.
  useEffect(() => {
    setIsRawExpanded(false);
    setIsLlmExpanded(false);
  }, [reportMeta]);

  const handleRescrape = async () => {
    if (!property) return;

    setRescrapingInProgress(true);
    try {
      const result = await forceRescrape(propertyId);
      addToast(result.message, "success");
    } catch (err) {
      console.error("Failed to trigger rescrape:", err);
      addToast("Failed to trigger rescrape", "error");
    } finally {
      setRescrapingInProgress(false);
    }
  };

  const handleAiValidate = async () => {
    if (!property) return;

    setAiValidateInProgress(true);
    try {
      const result = await forceAiValidate(propertyId);
      addToast(result.message, "success");
    } catch (err) {
      console.error("Failed to trigger AI validate:", err);
      addToast("Failed to trigger AI validate", "error");
    } finally {
      setAiValidateInProgress(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshingInProgress(true);
    try {
      const [propertyData, items] = await Promise.all([
        getPropertyDetail(propertyId),
        getPropertyReports(propertyId),
      ]);

      setProperty(propertyData);
      setReportMeta(items[0] ?? null);
      addToast("Property data refreshed", "success");
    } catch (err) {
      console.error("Failed to refresh property data:", err);
      addToast("Failed to refresh property data", "error");
    } finally {
      setRefreshingInProgress(false);
    }
  };

  const requestDeleteReport = (reportItem: PropertyReportListItem) => {
    if (!reportItem.can_delete) {
      addToast("Cannot delete a purchased report", "error");
      return;
    }
    setPendingDeleteReport(reportItem);
  };

  const handleViewPdf = async (
    reportItem: PropertyReportListItem,
    mode: "full" | "lite"
  ) => {
    const key = `${reportItem.id}:${mode}`;
    setViewingPdfKey(key);
    try {
      const payload = await getPropertyReportPdf(propertyId, reportItem.id, mode);

      const binary = atob(payload.pdf_base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }

      const blob = new Blob([bytes], {
        type: payload.content_type || "application/pdf",
      });
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);

      addToast(
        payload.generated
          ? `${payload.mode.toUpperCase()} PDF generated and cached in MinIO`
          : `Opened cached ${payload.mode.toUpperCase()} PDF`,
        "success"
      );
    } catch (err) {
      console.error("Failed to open report PDF:", err);
      addToast("Failed to generate/open report PDF", "error");
    } finally {
      setViewingPdfKey(null);
    }
  };

  const handleDeletePdfs = async (reportItem: PropertyReportListItem) => {
    setDeletingPdfReportId(reportItem.id);
    try {
      const result = await deletePropertyReportPdf(propertyId, reportItem.id, "all");
      addToast(result.message, "success");
    } catch (err) {
      console.error("Failed to delete cached report PDFs:", err);
      addToast("Failed to delete cached report PDFs", "error");
    } finally {
      setDeletingPdfReportId(null);
    }
  };

  const confirmDeleteReport = async () => {
    if (!pendingDeleteReport) return;
    const reportItem = pendingDeleteReport;

    setDeletingReportId(reportItem.id);
    try {
      const result = await deletePropertyReport(propertyId, reportItem.id);
      addToast(result.message, "success");

      const items = await getPropertyReports(propertyId);
      setReportMeta(items[0] ?? null);
      setPendingDeleteReport(null);
    } catch (err) {
      console.error("Failed to delete report:", err);
      addToast("Failed to delete report", "error");
    } finally {
      setDeletingReportId(null);
    }
  };

  const getConfidenceBadge = (
    confidence: "HIGH" | "MEDIUM" | "LOW" | null
  ) => {
    if (!confidence) return <span className="text-gray-500">—</span>;

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

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-center text-gray-400">Loading property...</div>
      </div>
    );
  }

  if (!property) {
    return (
      <div className="p-6">
        <div className="text-center text-gray-400">Property not found</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <button
            onClick={() => router.push("/properties")}
            className="text-blue-400 hover:text-blue-300 mb-2 text-sm"
          >
            ← Back to Properties
          </button>
          <h1 className="text-3xl font-bold text-white">
            {property.address_string}
          </h1>
          <p className="text-gray-400 mt-1">
            {property.suburb_name && `${property.suburb_name}, `}
            {property.state}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRescrape}
            disabled={rescrapingInProgress || aiValidateInProgress || refreshingInProgress}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
            {rescrapingInProgress ? "Queueing..." : "Re-scrape Property"}
          </button>
          <button
            onClick={handleAiValidate}
            disabled={aiValidateInProgress || rescrapingInProgress || refreshingInProgress}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
            {aiValidateInProgress ? "Queueing..." : "Re AI validate"}
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshingInProgress || aiValidateInProgress || rescrapingInProgress}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
            {refreshingInProgress ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Property Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Basic Information */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Basic Information
          </h2>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Property ID:</span>
              <span className="text-white font-mono text-sm">
                {property.id.slice(0, 8)}...
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">GNAF PID:</span>
              <span className="text-white">{property.gnaf_pid}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">State:</span>
              <span className="text-white">{property.state}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">LGA:</span>
              <span className="text-white">{property.lga_name || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Coordinates:</span>
              <span className="text-white font-mono text-sm">
                {property.latitude.toFixed(6)}, {property.longitude.toFixed(6)}
              </span>
            </div>
          </div>
        </div>

        {/* Metadata */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">Metadata</h2>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Last Scraped:</span>
              <span className="text-white">
                {property.last_scraped_at
                  ? new Date(property.last_scraped_at).toLocaleString()
                  : "Never"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Created:</span>
              <span className="text-white">
                {new Date(property.created_at).toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Updated:</span>
              <span className="text-white">
                {new Date(property.updated_at).toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Report Section */}
      <div className="bg-gray-800 rounded-lg p-6">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-white">Property Report</h2>
        </div>

        {reportMeta ? (
          <div className="space-y-4">
              {reportMeta && (reportMeta.status === "READY" || reportMeta.can_delete) && (
                <div className="rounded border border-gray-700 bg-gray-900 p-4">
                  <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleViewPdf(reportMeta, "full")}
                  disabled={!report?.llm_parsed_insights || viewingPdfKey === `${reportMeta.id}:full`}
                  className="px-3 py-1 bg-indigo-700 text-indigo-100 rounded hover:bg-indigo-600 transition-colors disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
                >
                  {viewingPdfKey === `${reportMeta.id}:full`
                    ? "Generating Full..."
                    : "View Full PDF"}
                </button>
                <button
                  onClick={() => handleViewPdf(reportMeta, "lite")}
                  disabled={!report?.llm_parsed_insights || viewingPdfKey === `${reportMeta.id}:lite`}
                  className="px-3 py-1 bg-cyan-700 text-cyan-100 rounded hover:bg-cyan-600 transition-colors disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
                >
                  {viewingPdfKey === `${reportMeta.id}:lite`
                    ? "Generating Lite..."
                    : "View Lite PDF"}
                </button>
                <button
                  onClick={() => handleDeletePdfs(reportMeta)}
                  disabled={deletingPdfReportId === reportMeta.id}
                  className="px-3 py-1 bg-amber-700 text-amber-100 rounded hover:bg-amber-600 transition-colors disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
                >
                  {deletingPdfReportId === reportMeta.id
                    ? "Deleting PDFs..."
                    : "Delete PDFs"}
                </button>
                <button
                  onClick={() => requestDeleteReport(reportMeta)}
                  disabled={!reportMeta.can_delete || deletingReportId === reportMeta.id}
                  className="px-3 py-1 bg-red-700 text-red-100 rounded hover:bg-red-600 transition-colors disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
                >
                  {deletingReportId === reportMeta.id ? "Deleting..." : "Delete"}
                </button>
                  </div>
                </div>
              )}

            <div className="rounded-md border border-gray-700 bg-gray-950 p-4 space-y-4">
              <div className="flex justify-between items-center gap-3">
                <h3 className="text-white font-semibold">Report Details</h3>
              </div>

              {loadingReport ? (
                <div className="text-center text-gray-400 py-8">Loading report...</div>
              ) : !report ? (
                <div className="text-center text-gray-400 py-8">
                  No report data available for this property.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-gray-900 rounded p-4">
                      <div className="text-gray-400 text-sm mb-1">Status</div>
                      <div className="text-white font-medium">{report.status}</div>
                    </div>
                    <div className="bg-gray-900 rounded p-4">
                      <div className="text-gray-400 text-sm mb-1">Confidence</div>
                      <div>{getConfidenceBadge(report.overall_confidence)}</div>
                    </div>
                  </div>

                  <div className="bg-gray-900 rounded p-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <span className="text-gray-400 text-sm">Created: </span>
                        <span className="text-white">
                          {new Date(report.created_at).toLocaleString()}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-400 text-sm">Updated: </span>
                        <span className="text-white">
                          {new Date(report.updated_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="rounded border border-gray-700 bg-gray-900">
                      <button
                        onClick={() => setIsRawExpanded((prev) => !prev)}
                        className="w-full text-left px-4 py-3 text-sm text-gray-100 hover:bg-gray-800 transition-colors"
                      >
                        {isRawExpanded
                          ? "Hide Raw Scraped Data"
                          : "Show Raw Scraped Data"}
                      </button>
                      {isRawExpanded && report.raw_scraped_data && (
                        <div className="border-t border-gray-700 p-3">
                          <JsonViewer
                            data={report.raw_scraped_data}
                            title="Raw Scraped Data"
                          />
                        </div>
                      )}
                      {isRawExpanded && !report.raw_scraped_data && (
                        <div className="border-t border-gray-700 p-3 text-sm text-gray-400">
                          No raw scraped data available.
                        </div>
                      )}
                    </div>

                    <div className="rounded border border-gray-700 bg-gray-900">
                      <button
                        onClick={() => setIsLlmExpanded((prev) => !prev)}
                        className="w-full text-left px-4 py-3 text-sm text-gray-100 hover:bg-gray-800 transition-colors"
                      >
                        {isLlmExpanded ? "Hide LLM Response" : "Show LLM Response"}
                      </button>
                      {isLlmExpanded && report.llm_parsed_insights && (
                        <div className="border-t border-gray-700 p-3">
                          <JsonViewer
                            data={report.llm_parsed_insights}
                            title="LLM Parsed Insights"
                          />
                        </div>
                      )}
                      {isLlmExpanded && !report.llm_parsed_insights && (
                        <div className="border-t border-gray-700 p-3 text-sm text-gray-400">
                          No LLM response available.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-center text-gray-400 py-6 bg-gray-900 rounded">
            No report available for this property yet.
          </div>
        )}
      </div>

      {pendingDeleteReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg bg-gray-800 border border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-white mb-2">Delete Report</h3>
            <p className="text-gray-300 text-sm mb-6">
              This will permanently delete the selected report. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setPendingDeleteReport(null)}
                disabled={deletingReportId === pendingDeleteReport.id}
                className="px-4 py-2 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteReport}
                disabled={deletingReportId === pendingDeleteReport.id}
                className="px-4 py-2 rounded bg-red-700 text-red-100 hover:bg-red-600 transition-colors disabled:opacity-50"
              >
                {deletingReportId === pendingDeleteReport.id
                  ? "Deleting..."
                  : "Delete Report"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
