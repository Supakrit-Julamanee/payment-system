import { getPublicKeyError } from "./config";

// Promise wrappers around the global `Omise` object from Omise.js.
// Card data goes from the browser straight to Omise. Never log the card,
// the token, or the Omise response.

export const OMISE_JS_URL = "https://cdn.omise.co/omise.js";

export interface OmiseCardInput {
  name: string;
  number: string;
  expiration_month: number;
  expiration_year: number;
  security_code: string;
}

// Only the fields this app reads. TODO: verify with Omise docs (spec §18).
interface OmiseResponse {
  id?: string;
  message?: string;
}

type OmiseCallback = (statusCode: number, response: OmiseResponse) => void;

interface OmiseJs {
  setPublicKey(key: string): void;
  createToken(type: "card", card: OmiseCardInput, callback: OmiseCallback): void;
  createSource(
    type: "promptpay",
    params: { amount: number; currency: string },
    callback: OmiseCallback,
  ): void;
}

declare global {
  interface Window {
    Omise?: OmiseJs;
  }
}

function getOmise(): OmiseJs {
  if (typeof window === "undefined" || !window.Omise) {
    throw new Error("Omise.js ยังโหลดไม่เสร็จ");
  }
  return window.Omise;
}

function toId(statusCode: number, response: OmiseResponse, fallbackMessage: string): string {
  if (statusCode !== 200 || !response.id) {
    throw new Error(response.message ?? fallbackMessage);
  }
  return response.id;
}

export function initOmise(publicKey: string): void {
  const keyError = getPublicKeyError();
  if (keyError) throw new Error(keyError);
  getOmise().setPublicKey(publicKey);
}

// Resolves to a token id (tokn_...).
export function createToken(card: OmiseCardInput): Promise<string> {
  return new Promise((resolve, reject) => {
    getOmise().createToken("card", card, (statusCode, response) => {
      try {
        resolve(toId(statusCode, response, "ไม่สามารถตรวจสอบข้อมูลบัตรได้"));
      } catch (err) {
        reject(err);
      }
    });
  });
}

// amount and currency must come from the Django order response, never from the UI.
// TODO: verify with Omise docs (spec §18) whether createSource needs other parameters.
// Resolves to a source id (src_...).
export function createPromptPaySource(amount: number, currency: string): Promise<string> {
  return new Promise((resolve, reject) => {
    getOmise().createSource("promptpay", { amount, currency }, (statusCode, response) => {
      try {
        resolve(toId(statusCode, response, "ไม่สามารถสร้างรายการ PromptPay ได้"));
      } catch (err) {
        reject(err);
      }
    });
  });
}
