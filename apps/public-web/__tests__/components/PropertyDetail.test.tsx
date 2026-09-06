import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import PropertyDetail from "@/components/property/PropertyDetail";
import NarrativeSection from "@/components/property/NarrativeSection";
import TrendAnalysisSection from "@/components/property/TrendAnalysisSection";
import InfrastructureList from "@/components/property/InfrastructureList";
import RoiScenariosSection from "@/components/property/RoiScenariosSection";
import type { PropertyDetail as PropertyDetailType } from "@/types";

let mockPropertyData: PropertyDetailType | null = null;
let mockIsLoading = false;

vi.mock("@/hooks/useProperty", () => ({
  useProperty: () => ({
    property: mockPropertyData,
    isLoading: mockIsLoading,
    mutate: vi.fn(),
  }),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    isSignedIn: true,
    isLoaded: true,
    getToken: vi.fn().mockResolvedValue("mock_token"),
  }),
  useUser: () => ({
    user: { id: "user_123" },
    isLoaded: true,
  }),
  SignInButton: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/api", () => ({
  useApiClient: () => ({
    get: vi.fn(),
    post: vi.fn(),
  }),
}));

vi.mock("@marsidev/react-turnstile", () => ({
  Turnstile: () => null,
}));

describe("PropertyDetail with Enriched LLM Data", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPropertyData = null;
    mockIsLoading = false;
    localStorage.setItem("ack_general_disclaimer", "true");
  });

  it("renders all 4 new sections when enriched data is present", async () => {
    mockPropertyData = {
      id: "prop-123",
      address: "10 Innovation Way, Clayton VIC 3168",
      state: "VIC",
      report_status: "READY",
      latitude: -37.9,
      longitude: 145.1,
      education: null,
      connectivity: null,
      risk_factors: null,
      zoning_and_planning: null,
      demographic_snapshot: null,
      narrative: {
        executive_summary: "High capital growth potential near employment clusters.",
        zoning_summary: "Commercial 1 zone allowing high-density residential.",
      },
      demographic_trend_analysis: {
        population_momentum: "ACCELERATING",
        population_momentum_note: "Rapid population expansion driven by tech jobs.",
        overall_investment_signal: "POSITIVE",
      },
      infrastructure: [
        {
          type: "TRANSPORT",
          description: "Suburban Rail Loop East station construction",
          distance_km: 0.6,
          expected_completion_year: 2035,
        },
      ],
      roi_scenarios: {
        disclaimer: "Returns are simulated and not guaranteed under Australian financial law.",
        scenarios: [
          {
            label: "Base",
            gross_yield_percent: 4.8,
            net_yield_percent: 3.9,
            annual_cash_flow_aud: 6500,
            assumptions: {
              weekly_rent_aud: 650,
              interest_rate_percent: 6.2,
            },
          },
        ],
      },
    };

    await act(async () => {
      render(<PropertyDetail propertyId="prop-123" />);
    });

    // Narrative Section
    expect(screen.getByText("AI Investment Narrative")).toBeInTheDocument();
    expect(screen.getByText("Executive Summary")).toBeInTheDocument();
    expect(
      screen.getByText("High capital growth potential near employment clusters.")
    ).toBeInTheDocument();

    // Trend Analysis Section
    expect(screen.getByText("Demographic Trend Analysis")).toBeInTheDocument();
    expect(screen.getByText("Population Momentum")).toBeInTheDocument();
    expect(screen.getByText("ACCELERATING")).toBeInTheDocument();

    // Infrastructure Section
    expect(screen.getByText("Nearby Infrastructure & Pipeline")).toBeInTheDocument();
    expect(
      screen.getByText("Suburban Rail Loop East station construction")
    ).toBeInTheDocument();
    expect(screen.getByText("Est. 2035")).toBeInTheDocument();

    // ROI Scenarios Section
    expect(
      screen.getByText("Projected ROI & Cash Flow Scenarios")
    ).toBeInTheDocument();
    expect(screen.getByText("Base Case")).toBeInTheDocument();
    expect(screen.getByText("4.80%")).toBeInTheDocument();
    expect(
      screen.getByText(/Returns are simulated and not guaranteed/)
    ).toBeInTheDocument();
  });

  it("omits the 4 new sections when data is absent/null (e.g. unauthenticated response)", async () => {
    mockPropertyData = {
      id: "prop-123",
      address: "10 Innovation Way, Clayton VIC 3168",
      state: "VIC",
      report_status: "READY",
      latitude: -37.9,
      longitude: 145.1,
      education: null,
      connectivity: { nbn_tech_type: "FTTP" },
      risk_factors: null,
      zoning_and_planning: null,
      demographic_snapshot: null,
      narrative: null,
      demographic_trend_analysis: null,
      infrastructure: null,
      roi_scenarios: null,
    };

    await act(async () => {
      render(<PropertyDetail propertyId="prop-123" />);
    });

    expect(screen.getByText("Connectivity")).toBeInTheDocument();
    expect(screen.queryByText("AI Investment Narrative")).not.toBeInTheDocument();
    expect(screen.queryByText("Demographic Trend Analysis")).not.toBeInTheDocument();
    expect(screen.queryByText("Nearby Infrastructure & Pipeline")).not.toBeInTheDocument();
    expect(screen.queryByText("Projected ROI & Cash Flow Scenarios")).not.toBeInTheDocument();
  });
});

describe("Individual Section Components", () => {
  it("NarrativeSection returns null when empty", () => {
    const { container } = render(<NarrativeSection narrative={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("TrendAnalysisSection renders badges and notes properly", () => {
    render(
      <TrendAnalysisSection
        analysis={{
          population_momentum: "ACCELERATING",
          population_momentum_note: "Population growing steadily.",
          overall_investment_signal: "POSITIVE",
        }}
      />
    );
    expect(screen.getByText("ACCELERATING")).toBeInTheDocument();
    expect(screen.getByText("Population growing steadily.")).toBeInTheDocument();
  });

  it("InfrastructureList renders items and skips when empty", () => {
    const { container: emptyContainer } = render(
      <InfrastructureList infrastructure={[]} />
    );
    expect(emptyContainer.firstChild).toBeNull();

    render(
      <InfrastructureList
        infrastructure={[
          {
            type: "HEALTH",
            description: "New Clayton Community Hospital",
            distance_km: 1.2,
            source_url: "https://example.com/hospital",
          },
        ]}
      />
    );
    expect(screen.getByText("HEALTH")).toBeInTheDocument();
    expect(screen.getByText("New Clayton Community Hospital")).toBeInTheDocument();
    expect(screen.getByText("Source")).toHaveAttribute(
      "href",
      "https://example.com/hospital"
    );
  });

  it("RoiScenariosSection renders scenario metrics and prominent disclaimer", () => {
    render(
      <RoiScenariosSection
        roiScenarios={{
          disclaimer: "Mandatory AFSL disclaimer: past performance is not indicative of future returns.",
          scenarios: [
            {
              label: "Conservative",
              gross_yield_percent: 3.5,
              net_yield_percent: 2.8,
              annual_cash_flow_aud: 3200,
              assumptions: {
                interest_rate_percent: 6.8,
                weekly_rent_aud: 550,
              },
            },
          ],
        }}
      />
    );
    expect(screen.getByText("Conservative Case")).toBeInTheDocument();
    expect(screen.getByText("3.50%")).toBeInTheDocument();
    expect(screen.getByText("2.80%")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(
      "Mandatory AFSL disclaimer"
    );
  });
});
