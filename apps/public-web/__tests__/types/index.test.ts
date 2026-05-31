import { describe, it, expect } from "vitest";
import { ApiError } from "@/types";

describe("Types", () => {
  describe("ApiError", () => {
    it("creates error with status and message", () => {
      const err = new ApiError(404, "Not found");
      expect(err.status).toBe(404);
      expect(err.message).toBe("Not found");
      expect(err.name).toBe("ApiError");
    });

    it("is an instance of Error", () => {
      const err = new ApiError(500, "Server error");
      expect(err).toBeInstanceOf(Error);
      expect(err).toBeInstanceOf(ApiError);
    });
  });
});
