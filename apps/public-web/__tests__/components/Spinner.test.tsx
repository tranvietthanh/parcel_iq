import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Spinner from "@/components/ui/Spinner";

describe("Spinner", () => {
  it("renders with default size", () => {
    render(<Spinner />);
    const svg = screen.getByRole("status");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveClass("h-6", "w-6");
  });

  it("renders small size", () => {
    render(<Spinner size="sm" />);
    const svg = screen.getByRole("status");
    expect(svg).toHaveClass("h-4", "w-4");
  });

  it("renders large size", () => {
    render(<Spinner size="lg" />);
    const svg = screen.getByRole("status");
    expect(svg).toHaveClass("h-8", "w-8");
  });

  it("has accessible label", () => {
    render(<Spinner />);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });
});
