"""
generate_data.py
----------------
Generates synthetic gift card issuance and redemption datasets that mimic
real-world gift card lifecycle behavior: cards issued to customers, redeemed
over time (partially or fully), sometimes never redeemed, sometimes voided,
with deliberate data-quality edge cases baked in.

This is fully synthetic. No real customer, card, or transaction data is used.

Output:
    data/giftcard_issuance.csv    (~3200 rows)
    data/giftcard_redemption.csv  (~3800 rows)
"""

import csv
import random
from datetime import date, timedelta

random.seed(42)  # reproducible dataset

ISSUANCE_FILE = "data/giftcard_issuance.csv"
REDEMPTION_FILE = "data/giftcard_redemption.csv"
TARGET_CARDS = 3200

CURRENCIES = ["USD", "USD", "USD", "USD", "EUR", "GBP"]
CARD_EXPIRATION_MONTHS = 24  # policy: cards expire 24 months after issuance

START_DATE = date(2022, 1, 1)
END_DATE = date(2024, 12, 31)


def random_issuance_date():
    span = (END_DATE - START_DATE).days
    return START_DATE + timedelta(days=random.randint(0, span))


def add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def make_card_id(n):
    return f"GC-{500000 + n}"


def make_customer_id(n):
    return f"CUST-{n:05d}"


def make_redemption_id(card_id, seq):
    return f"{card_id}-R{seq}"


class Card:
    def __init__(self, card_id, customer_id, issuance_date, issued_amount, currency, status="ACTIVE"):
        self.card_id = card_id
        self.customer_id = customer_id
        self.issuance_date = issuance_date
        self.issued_amount = issued_amount
        self.currency = currency
        self.status = status
        self.redemptions = []  # list of (redemption_date, amount)

    def issuance_row(self):
        return {
            "card_id": self.card_id,
            "customer_id": self.customer_id,
            "issuance_date": self.issuance_date.isoformat(),
            "issued_amount": self.issued_amount,
            "currency": self.currency,
            "status": self.status,
        }

    def redemption_rows(self):
        rows = []
        for i, (rdate, amount) in enumerate(self.redemptions, start=1):
            rows.append({
                "redemption_id": make_redemption_id(self.card_id, i),
                "card_id": self.card_id,
                "redemption_date": rdate.isoformat(),
                "redemption_amount": amount,
            })
        return rows


def scenario_full_redemption_single(card, n):
    """Card redeemed in full in a single transaction, within a few months."""
    r_date = add_months(card.issuance_date, random.randint(0, 6))
    card.redemptions.append((r_date, card.issued_amount))
    return card


def scenario_partial_redemptions(card, n):
    """Multiple partial redemptions draining the card over time."""
    remaining = card.issued_amount
    n_txns = random.randint(2, 4)
    months_elapsed = 0
    for i in range(n_txns):
        months_elapsed += random.randint(1, 5)
        r_date = add_months(card.issuance_date, months_elapsed)
        if r_date > END_DATE:
            break
        if i == n_txns - 1:
            amount = remaining
        else:
            amount = round(remaining * random.uniform(0.2, 0.5), 2)
            amount = min(amount, remaining)
        if amount <= 0:
            break
        card.redemptions.append((r_date, amount))
        remaining = round(remaining - amount, 2)
    return card


def scenario_never_redeemed(card, n):
    """Card never redeemed at all - pure breakage candidate."""
    return card


def scenario_same_month_redemption(card, n):
    """Issued and fully redeemed within the same calendar month."""
    r_date = card.issuance_date + timedelta(days=random.randint(1, 20))
    card.redemptions.append((r_date, card.issued_amount))
    return card


def scenario_long_dormancy(card, n):
    """Card sits dormant for 12+ months before being redeemed."""
    months_elapsed = random.randint(12, 20)
    r_date = add_months(card.issuance_date, months_elapsed)
    if r_date <= END_DATE:
        card.redemptions.append((r_date, card.issued_amount))
    return card


def scenario_voided_card(card, n):
    """Card issued then voided/cancelled shortly after - no redemptions expected."""
    card.status = "VOIDED"
    return card


def scenario_overdraft_redemption(card, n):
    """Data-quality edge case: a redemption amount that (due to an upstream
    system error) exceeds the card's remaining balance. The mart must cap
    redeemed amount at issued_amount rather than allow negative remaining
    balance."""
    r_date = add_months(card.issuance_date, random.randint(0, 3))
    inflated_amount = round(card.issued_amount * random.uniform(1.05, 1.25), 2)
    card.redemptions.append((r_date, inflated_amount))
    return card


def scenario_refund_adjustment(card, n):
    """Card redeemed, then a negative-amount redemption (refund/reversal)
    partially restores balance."""
    r_date1 = add_months(card.issuance_date, random.randint(0, 4))
    redeem_amount = round(card.issued_amount * random.uniform(0.5, 0.9), 2)
    card.redemptions.append((r_date1, redeem_amount))
    r_date2 = r_date1 + timedelta(days=random.randint(2, 15))
    refund_amount = -round(redeem_amount * random.uniform(0.2, 0.5), 2)
    card.redemptions.append((r_date2, refund_amount))
    return card


def scenario_expiring_breakage(card, n):
    """Partially redeemed, then the card expires (24 months) with remaining
    balance becoming breakage. Mart logic must recognize expiration as an
    end-state, not ongoing dormancy."""
    r_date = add_months(card.issuance_date, random.randint(1, 6))
    partial = round(card.issued_amount * random.uniform(0.3, 0.6), 2)
    card.redemptions.append((r_date, partial))
    return card


SCENARIOS = [
    (scenario_full_redemption_single, 0.28),
    (scenario_partial_redemptions, 0.24),
    (scenario_never_redeemed, 0.18),
    (scenario_same_month_redemption, 0.08),
    (scenario_long_dormancy, 0.08),
    (scenario_voided_card, 0.04),
    (scenario_overdraft_redemption, 0.03),
    (scenario_refund_adjustment, 0.03),
    (scenario_expiring_breakage, 0.00),  # weight fixed below to absorb remainder
]

_fixed = [w for _, w in SCENARIOS[:-1]]
SCENARIOS[-1] = (scenario_expiring_breakage, round(1 - sum(_fixed), 4))


def pick_scenario():
    funcs, weights = zip(*SCENARIOS)
    return random.choices(funcs, weights=weights, k=1)[0]


def generate():
    issuance_rows = []
    redemption_rows = []

    # Give a subset of customers multiple cards (edge case: repeat customers)
    customer_pool = [make_customer_id(i) for i in range(1, int(TARGET_CARDS * 0.75))]

    for i in range(1, TARGET_CARDS + 1):
        card_id = make_card_id(i)
        customer_id = random.choice(customer_pool)
        issuance_date = random_issuance_date()
        currency = random.choice(CURRENCIES)
        issued_amount = round(random.choice([25, 50, 75, 100, 150, 200]) * random.uniform(0.9, 1.0), 2)

        card = Card(card_id, customer_id, issuance_date, issued_amount, currency)
        scenario_fn = pick_scenario()
        card = scenario_fn(card, i)

        issuance_rows.append(card.issuance_row())
        redemption_rows.extend(card.redemption_rows())

    with open(ISSUANCE_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["card_id", "customer_id", "issuance_date", "issued_amount", "currency", "status"])
        writer.writeheader()
        writer.writerows(issuance_rows)

    with open(REDEMPTION_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["redemption_id", "card_id", "redemption_date", "redemption_amount"])
        writer.writeheader()
        writer.writerows(redemption_rows)

    print(f"Generated {len(issuance_rows)} cards -> {ISSUANCE_FILE}")
    print(f"Generated {len(redemption_rows)} redemption transactions -> {REDEMPTION_FILE}")


if __name__ == "__main__":
    generate()
