import { ApiError } from "@/types";

// Server components hit the backend directly
const SERVER_API_URL = process.env.INTERNAL_API_URL ?? "http://localhost:8080";

export async function serverApiRequest<T>(
  path: string,
  getToken: () => Promise<string | null>,
): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${SERVER_API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, err.detail ?? "Request failed");
  }

  return res.json();
}
