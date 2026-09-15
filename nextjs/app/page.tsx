import { PRODUCTS } from "@/lib/products";
import BuyButton from "./BuyButton";

export default function Home() {
  return (
    <main className="container">
      <h1>สินค้า</h1>
      <p className="muted">เลือกสินค้า 1 ชิ้น ราคาจะแสดงในหน้าชำระเงินตามที่ระบบหลังบ้านกำหนด</p>
      <ul className="products">
        {PRODUCTS.map((product) => (
          <li key={product.id} className="card product">
            <span className="summary-name">{product.name}</span>
            <BuyButton productId={product.id} />
          </li>
        ))}
      </ul>
    </main>
  );
}
