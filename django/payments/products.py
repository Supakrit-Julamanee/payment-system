"""Product catalog (spec §5.2). The backend is the only source of prices."""

# Amounts are integer satang (1 THB = 100 satang). Never use float.
# PromptPay's minimum charge is 2000 satang (฿20), verified 2026-09-16 against
# https://docs.omise.co/promptpay, so both prices below are above it.
PRODUCTS = {
    "coffee": {"name": "Coffee", "amount": 6000},  # 60.00 THB
    "cake": {"name": "Cake", "amount": 12000},  # 120.00 THB
}

CURRENCY = "thb"
