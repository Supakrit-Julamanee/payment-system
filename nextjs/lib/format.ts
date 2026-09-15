// `amount` is an integer in satang (6000 = 60.00 THB). Format it without float math.
export function formatAmount(amount: number, currency = "thb"): string {
  const major = Math.floor(amount / 100).toLocaleString("en-US");
  const minor = String(amount % 100).padStart(2, "0");
  return `${major}.${minor} ${currency.toUpperCase()}`;
}

export function formatCountdown(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}
