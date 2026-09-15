"""Product catalog (spec §5.2). The backend is the only source of prices."""

# Amounts are integer satang (1 THB = 100 satang). Never use float.
# TODO: verify with Omise docs (spec §18) that every amount is at or above
# Omise's minimum charge for both card and PromptPay.
PRODUCTS = {
    "coffee": {"name": "Coffee", "amount": 6000},  # 60.00 THB
    "cake": {"name": "Cake", "amount": 12000},  # 120.00 THB
}

CURRENCY = "thb"
