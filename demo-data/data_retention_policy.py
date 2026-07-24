"""
Nightly data retention purge job.

Implements the schedule described in the company's Data Retention Policy:
financial records are kept 7 years, employee records 3 years after
termination, and customer support tickets 2 years, after which each
category is deleted by this job rather than by manual review.
"""

FINANCIAL_RECORDS_RETENTION_YEARS = 7
EMPLOYEE_RECORDS_RETENTION_YEARS_POST_TERMINATION = 3
SUPPORT_TICKET_RETENTION_YEARS = 2


def purge_expired_records(records, retention_years, reference_date):
    """Returns the subset of `records` older than `retention_years` relative
    to `reference_date`. A real deployment would delete these; this stub
    only selects them, so the policy stays auditable before anything is
    actually removed."""
    cutoff_year = reference_date.year - retention_years
    return [r for r in records if r.get("year", cutoff_year) < cutoff_year]
