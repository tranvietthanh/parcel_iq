import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MyPropertiesPage from "@/app/my-properties/page";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockApiClient = {
  get: mockGet,
  post: mockPost,
};

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    isSignedIn: true,
    isLoaded: true,
  }),
  SignInButton: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/api", () => ({
  useApiClient: () => mockApiClient,
}));

vi.mock("@marsidev/react-turnstile", () => ({
  Turnstile: () => null,
}));

describe("MyPropertiesPage RequestedTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders failed property row with Retry button", async () => {
    mockGet.mockResolvedValueOnce({
      items: [
        {
          property_id: "prop-123",
          address: "182, BOUNDARY ROAD, PASCOE VALE, VIC 3044",
          state: "VIC",
          report_id: "rep-123",
          report_status: "FAILED",
          requested_at: "2026-08-22T09:07:45Z",
          ready_at: null,
          has_downloaded_before: false,
          slug: null,
        },
      ],
      pagination: {
        page: 1,
        page_size: 20,
        total_count: 1,
        total_pages: 1,
      },
    });

    render(<MyPropertiesPage />);

    await waitFor(() => {
      expect(screen.getByText("182, BOUNDARY ROAD, PASCOE VALE, VIC 3044")).toBeInTheDocument();
      expect(screen.getByText("Failed")).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  it("triggers request-scrape on clicking Retry", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          property_id: "prop-123",
          address: "182, BOUNDARY ROAD, PASCOE VALE, VIC 3044",
          state: "VIC",
          report_id: "rep-123",
          report_status: "FAILED",
          requested_at: "2026-08-22T09:07:45Z",
          ready_at: null,
          has_downloaded_before: false,
          slug: null,
        },
      ],
      pagination: {
        page: 1,
        page_size: 20,
        total_count: 1,
        total_pages: 1,
      },
    });
    mockPost.mockResolvedValue({ status: "queued" });

    render(<MyPropertiesPage />);

    const retryBtn = await screen.findByTitle("Retry processing for this property");
    expect(retryBtn).toBeInTheDocument();

    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/properties/prop-123/request-scrape",
        {},
        undefined
      );
    });
  });

  it("renders View link for READY property", async () => {
    mockGet.mockResolvedValueOnce({
      items: [
        {
          property_id: "prop-456",
          address: "1, WICKLOW STREET, PASCOE VALE, VIC 3044",
          state: "VIC",
          report_id: "rep-456",
          report_status: "READY",
          requested_at: "2026-06-18T00:00:00Z",
          ready_at: "2026-06-18T00:05:00Z",
          has_downloaded_before: false,
          slug: "1-wicklow-street-pascoe-vale-vic-3044-4dd3ccf5",
        },
      ],
      pagination: {
        page: 1,
        page_size: 20,
        total_count: 1,
        total_pages: 1,
      },
    });

    render(<MyPropertiesPage />);

    await waitFor(() => {
      expect(screen.getByText("Ready")).toBeInTheDocument();
      expect(screen.getByText("View →")).toBeInTheDocument();
    });
  });
});
