"""
Generates the seed PDFs used in the recruiter demo and in local development.

Run with: python3 generate_demo_pdfs.py
Requires PyMuPDF (already a backend dependency): pip install pymupdf
"""
import textwrap
from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).parent

DOCUMENTS = {
    "Expense_Policy.pdf": [
        (
            "Corporate Expense Policy",
            [
                "1. Purpose",
                "This policy defines how employees submit, approve, and get reimbursed for "
                "business expenses incurred while performing company duties.",
                "",
                "2. Scope",
                "This policy applies to all full-time and part-time employees across every "
                "department, including Engineering, Sales, Operations, and Finance.",
            ],
        ),
        (
            "Approval Thresholds",
            [
                "3. Approval Thresholds",
                "Individual contributors may approve expenses up to $500 per request without "
                "additional sign-off.",
                "",
                "Department managers may approve expenses up to a threshold of $5,000 per "
                "request without additional sign-off.",
                "",
                "Any request exceeding $5,000 requires written approval from a Vice President "
                "or the Chief Financial Officer before reimbursement is processed.",
            ],
        ),
        (
            "Reimbursement Timeline",
            [
                "4. Reimbursement Timeline",
                "Approved reimbursements are processed within 10 business days of submission "
                "through the finance portal.",
                "",
                "5. Travel Expenses",
                "Airfare must be booked in economy class for flights under 6 hours. Hotel "
                "bookings should not exceed $220 per night in standard cost-of-living cities.",
            ],
        ),
    ],
    "Employee_Handbook_Excerpt.pdf": [
        (
            "Remote Work Policy",
            [
                "Remote Work Policy",
                "Employees may work remotely up to three days per week, subject to manager "
                "approval and team coverage requirements.",
                "",
                "Employees working remotely must be reachable during core hours, defined as "
                "10:00 AM to 4:00 PM in their local time zone.",
            ],
        ),
        (
            "Paid Time Off",
            [
                "Paid Time Off (PTO)",
                "Full-time employees accrue 18 days of paid time off per year, credited "
                "monthly at a rate of 1.5 days.",
                "",
                "Unused PTO up to 5 days may be carried over into the following calendar year. "
                "Any remaining balance beyond that is forfeited.",
            ],
        ),
    ],
    "Vendor_Contract_Summary.pdf": [
        (
            "Vendor Agreement Overview",
            [
                "Vendor Agreement Summary — CloudOps Services Inc.",
                "This agreement covers managed infrastructure support services provided to "
                "the company for a 12-month term beginning January 1.",
                "",
                "Service Level Agreement (SLA): 99.9% monthly uptime, with credits issued for "
                "any month falling below that threshold.",
            ],
        ),
        (
            "Termination Clause",
            [
                "Termination",
                "Either party may terminate this agreement with 60 days written notice. Early "
                "termination by the company before month 6 incurs an early-exit fee equal to "
                "one month of service fees.",
            ],
        ),
    ],
}


def build_pdf(filename: str, sections: list[tuple[str, list[str]]]) -> None:
    doc = fitz.open()
    for heading, lines in sections:
        page = doc.new_page()
        y = 72
        page.insert_text((72, y), heading, fontsize=15, fontname="helv")
        y += 30
        for line in lines:
            if not line:
                y += 12
                continue
            wrapped = textwrap.wrap(line, width=95)
            for wline in wrapped:
                page.insert_text((72, y), wline, fontsize=10.5, fontname="helv")
                y += 16
    doc.save(str(OUT_DIR / filename))
    doc.close()


if __name__ == "__main__":
    for filename, sections in DOCUMENTS.items():
        build_pdf(filename, sections)
        print(f"wrote {filename}")
