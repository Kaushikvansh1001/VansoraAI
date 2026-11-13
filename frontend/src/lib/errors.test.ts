import { describe, expect, it } from "vitest";
import { errorFromBody } from "./errors";

describe("errorFromBody", () => {
  it("reads the API error envelope", () => {
    const error = errorFromBody(
      { error: { code: "forbidden", message: "You do not have access to that organization." } },
      403,
    );
    expect(error.code).toBe("forbidden");
    expect(error.message).toBe("You do not have access to that organization.");
    expect(error.status).toBe(403);
  });

  it("falls back when the body is empty", () => {
    const error = errorFromBody(null, 500);
    expect(error.code).toBe("request_failed");
    expect(error.status).toBe(500);
  });
});
