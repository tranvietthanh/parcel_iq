"""DECOMMISSIONED — payments.py

This router has been removed as part of the credit-based-downloads change.
The GET /api/payments/status/{property_id} endpoint is replaced by:

  - GET /api/credits/me              — wallet summary
  - GET /api/properties/{id}/full/precheck — duplicate-download advisory check

See: app/routers/credits.py, app/routers/my_properties.py
"""

raise ImportError(
    "payments.py is decommissioned. Credit status is served by credits.py."
)
