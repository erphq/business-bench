import { describe, expect, test } from "bun:test";
import worker from "../worker.js";

describe("canonical host redirects", () => {
  test.each([
    "http://businessbench.org",
    "http://www.businessbench.org",
    "https://www.businessbench.org",
  ])("consolidates %s without changing paths or query parameters", async (origin) => {
    for (const path of ["/", "/tasks/rent-roll-build", "/paper?utm_source=search&x=a%2Fb", "/sitemap-index.xml"]) {
      const response = await worker.fetch(new Request(origin + path), {
        ASSETS: { fetch() { throw new Error("Alternate hosts must redirect before serving assets"); } },
      });
      expect(response.status).toBe(308);
      expect(response.headers.get("location")).toBe("https://businessbench.org" + path);
    }
  });

  test("does not turn a path into an external redirect", async () => {
    const response = await worker.fetch(new Request("http://www.businessbench.org//example.com/path"), {
      ASSETS: { fetch() { throw new Error("Unexpected asset fetch"); } },
    });
    expect(response.headers.get("location")).toBe("https://businessbench.org//example.com/path");
  });

  test.each(["https://businessbench.org", "http://localhost:4321", "http://127.0.0.1:8787"])(
    "passes %s to assets with response status and headers intact", async (origin) => {
      for (const status of [200, 301, 404]) {
        const request = new Request(origin + "/sitemap.xml", { method: "HEAD" });
        const assetResponse = new Response(null, { status, headers: { "x-check": "preserved" } });
        const response = await worker.fetch(request, {
          ASSETS: { fetch(received: Request) { expect(received).toBe(request); return Promise.resolve(assetResponse); } },
        });
        expect(response).toBe(assetResponse);
      }
    },
  );
});
