"""Shared pytest configuration.

Billing routes now have a single canonical owner in ``app.api.billing_lifecycle``.
Tests patch that module directly; no legacy route bridge is intentionally kept.
"""
