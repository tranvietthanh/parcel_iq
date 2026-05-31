"""DECOMMISSIONED — quota.py

This module has been removed as part of the credit-based-downloads change.
Subscription-tier download quotas are replaced by the credit ledger system.

See: app/core/credits.py
Migration: 025_credit_anon_claim_and_cleanup.py (drops daily_downloads table)
"""

raise ImportError(
    "quota.py is decommissioned. Use app.core.credits for credit operations."
)
