import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardView } from "../DashboardPage";

describe("DashboardView", () => {
  it("renders loading state", () => {
    render(
      <DashboardView
        health={null}
        packages={[]}
        runs={[]}
        schedules={[]}
        providers={[]}
        loading
        error={null}
      />,
    );

    expect(screen.getByText(/loading platform dashboard/i)).toBeInTheDocument();
  });

  it("renders empty states when no data is present", () => {
    render(
      <DashboardView
        health={{ status: "ok", service: "api", timestamp: new Date().toISOString() }}
        packages={[]}
        runs={[]}
        schedules={[]}
        providers={[]}
        loading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no schedules configured/i)).toBeInTheDocument();
    expect(screen.getByText(/no providers configured/i)).toBeInTheDocument();
  });
});