// NEXT_PUBLIC_* values are inlined at build time, so they must be referenced literally.
export const OMISE_PUBLIC_KEY: string = process.env.NEXT_PUBLIC_OMISE_PUBLIC_KEY ?? "";

export const API_BASE_URL: string = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

// Test-mode guard (spec §4): checkout must never load with a live or missing key.
export function getPublicKeyError(): string | null {
  if (!OMISE_PUBLIC_KEY) {
    return "NEXT_PUBLIC_OMISE_PUBLIC_KEY is not set.";
  }
  if (!OMISE_PUBLIC_KEY.startsWith("pkey_test_")) {
    return "NEXT_PUBLIC_OMISE_PUBLIC_KEY must be a test key (pkey_test_...). Checkout is disabled.";
  }
  return null;
}
