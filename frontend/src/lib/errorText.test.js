/**
 * Unit tests for errorText() — the crash-guard that turns any FastAPI
 * error into a plain string. Prevents "Objects are not valid as a React
 * child" when a backend returns `HTTPException(detail={...})`.
 *
 * Run with:
 *   cd /app/frontend && CI=true yarn test --watchAll=false src/lib/errorText.test.js
 */
import { errorText } from "./api";

describe("errorText", () => {
  test("returns string detail as-is", () => {
    expect(errorText({ response: { data: { detail: "Invalid password" } } })).toBe("Invalid password");
  });

  test("extracts .message from an object detail (the crash case)", () => {
    const err = {
      response: {
        status: 403,
        data: { detail: { message: "Please change your password first.", password_change_required: true } },
      },
    };
    expect(errorText(err)).toBe("Please change your password first.");
  });

  test("extracts pydantic v2 validation msg from an array detail", () => {
    const err = {
      response: {
        data: {
          detail: [
            { loc: ["body", "email"], msg: "value is not a valid email", type: "value_error.email" },
          ],
        },
      },
    };
    expect(errorText(err)).toBe("value is not a valid email");
  });

  test("falls back to err.message when detail is missing", () => {
    expect(errorText({ message: "Network Error" })).toBe("Network Error");
  });

  test("uses supplied fallback when nothing informative is present", () => {
    expect(errorText({}, "Try again")).toBe("Try again");
    expect(errorText(null, "Try again")).toBe("Try again");
  });

  test("never returns an object (regression guard for the React child crash)", () => {
    const err = { response: { data: { detail: { a: 1, b: 2 } } } };
    const out = errorText(err);
    expect(typeof out).toBe("string");
  });
});
