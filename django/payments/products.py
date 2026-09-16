"""Product catalog (spec §5.2). The backend is the only source of prices."""

# Amounts are integer satang (1 THB = 100 satang). Never use float.
# Omise's THB minimum is 2000 satang (฿20) for both card and PromptPay, verified 2026-09-16
# against https://docs.omise.co/currency-and-amount and a real test charge (1999 was
# rejected, 2000 accepted), so both prices below are above it.
PRODUCTS = {
    "coffee": {"name": "Coffee", "amount": 6000},  # 60.00 THB
    "cake": {"name": "Cake", "amount": 12000},  # 120.00 THB
}

CURRENCY = "thb"
