// Display list only. Prices are intentionally not here: the backend `PRODUCTS`
// (spec §5.2) is the only source of the amount, and checkout shows the amount
// returned by Django. Keep these ids in sync with backend `PRODUCTS`.
export interface ProductListing {
  id: string;
  name: string;
}

export const PRODUCTS: readonly ProductListing[] = [
  { id: "coffee", name: "Coffee" },
  { id: "cake", name: "Cake" },
];
