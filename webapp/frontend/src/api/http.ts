// src/api/http.ts
export class HttpError extends Error {
  status: number;
  statusText: string;
  bodyText?: string;

  constructor(args: { status: number; statusText: string; bodyText?: string }) {
    super(
      `Request failed: ${args.status} ${args.statusText}${args.bodyText ? " - " + args.bodyText : ""}`
    );
    this.name = "HttpError";
    this.status = args.status;
    this.statusText = args.statusText;
    this.bodyText = args.bodyText;
  }
}

/**
 * Fetch wrapper that returns JSON when present.
 * - Works with 204 No Content
 * - Works with empty-body 200 responses
 */
export async function requestJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new HttpError({
      status: res.status,
      statusText: res.statusText,
      bodyText: text || undefined,
    });
  }

  // Handle empty body / 204 gracefully
  if (res.status === 204) return undefined as T;

  const text = await res.text().catch(() => "");
  if (!text) return undefined as T;

  return JSON.parse(text) as T;
}

export function toQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}
