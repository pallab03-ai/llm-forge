import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "@/components/monitoring/pagination";

describe("Pagination", () => {
  it("disables Previous on the first page", () => {
    render(<Pagination total={120} limit={50} offset={0} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next page/i })).not.toBeDisabled();
  });

  it("disables Next on the last page", () => {
    render(<Pagination total={120} limit={50} offset={100} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /next page/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /previous page/i })).not.toBeDisabled();
  });

  it("calls onChange with the new offset when Next is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Pagination total={120} limit={50} offset={0} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /next page/i }));
    expect(onChange).toHaveBeenCalledWith({ limit: 50, offset: 50 });
  });

  it("calls onChange with the new offset when Previous is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Pagination total={120} limit={50} offset={50} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /previous page/i }));
    expect(onChange).toHaveBeenCalledWith({ limit: 50, offset: 0 });
  });

  it("shows the current page and total count", () => {
    render(<Pagination total={125} limit={50} offset={50} onChange={vi.fn()} />);
    expect(screen.getByText(/page 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByText(/125 total/i)).toBeInTheDocument();
  });
});
