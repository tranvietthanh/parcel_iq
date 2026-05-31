import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MetricCard from "@/components/property/MetricCard";

describe("MetricCard", () => {
  it("renders label and value", () => {
    render(<MetricCard label="Beds" value={3} />);
    expect(screen.getByText("Beds")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders dash for null value", () => {
    render(<MetricCard label="Cars" value={null} />);
    expect(screen.getByText("Cars")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders with prefix and suffix", () => {
    render(<MetricCard label="Yield" value={5.2} suffix="%" />);
    expect(screen.getByText("5.2%")).toBeInTheDocument();
  });

  it("renders compact format for large numbers", () => {
    render(
      <MetricCard
        label="Est. Value"
        value={1500000}
        prefix="$"
        format="compact"
      />,
    );
    expect(screen.getByText("Est. Value")).toBeInTheDocument();
    // Intl.NumberFormat compact: 1.5M
    const valueEl = screen.getByText(/\$1\.5M/);
    expect(valueEl).toBeInTheDocument();
  });
});
