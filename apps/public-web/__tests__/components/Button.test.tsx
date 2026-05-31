import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Button from "@/components/ui/Button";

describe("Button", () => {
  it("renders children text", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText("Click me")).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    let clicked = false;
    render(<Button onClick={() => (clicked = true)}>Click</Button>);
    fireEvent.click(screen.getByText("Click"));
    expect(clicked).toBe(true);
  });

  it("is disabled when disabled prop is set", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByText("Disabled")).toBeDisabled();
  });

  it("is disabled when loading", () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByText("Loading").closest("button")).toBeDisabled();
  });

  it("applies variant styles", () => {
    const { container } = render(
      <Button variant="secondary">Secondary</Button>,
    );
    const button = container.querySelector("button");
    expect(button).toHaveClass("bg-zinc-100");
  });

  it("applies size styles", () => {
    const { container } = render(<Button size="lg">Large</Button>);
    const button = container.querySelector("button");
    expect(button).toHaveClass("px-6");
  });
});
