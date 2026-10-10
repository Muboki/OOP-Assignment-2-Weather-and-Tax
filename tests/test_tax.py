# Import tools for exact amounts, calculation dates and automated tests.
from decimal import Decimal
from datetime import date

# Import tools for generating reproducible property-based test examples.
from hypothesis import given, settings, strategies as st

import pytest

# Import the tax classes and custom exceptions used by our tests.
from src.tax import (
    CorporateTax,
    InvalidIncomeError,
    Invoice,
    Money,
    NoScheduleForDateError,
    PayeTax,
    Payroll,
    TaxContext,
    TaxError,
    TaxPlanner,
    VatTax
)


# Check resident PAYE at the assignment's required boundary values.
@pytest.mark.parametrize(
    "income, expected_tax",
    [
        ("335000", "0.00"),
        ("335001", "0.20"),
        ("410000", "15000.00"),
        ("485000", "33750.00"),
        ("10000000", "2888250.00"),
        ("10000001", "2888250.40"),
    ]
)
def test_resident_paye_boundaries(
    income: str,
    expected_tax: str
) -> None:
    """Verify the tax calculated at each specified resident band boundary."""
    context = TaxContext(
        income=Money(income),
        tax_date=date(2026, 10, 31),
        resident=True
    )

    result = PayeTax().calculate(context)

    assert result.tax_amount.amount == Decimal(expected_tax)

    # Generate non-negative incomes with up to two decimal places.
income_values = st.decimals(
    min_value="0",
    max_value="100000000",
    places=2,
    allow_nan=False,
    allow_infinity=False
)


# Check that PAYE stays between zero and chargeable income.
@settings(max_examples=100, derandomize=True)
@given(income=income_values, resident=st.booleans())
def test_paye_within_income(income: Decimal, resident: bool) -> None:
    """Tax must be non-negative and must not exceed income."""
    context = TaxContext(
        income=Money(income),
        tax_date=date(2026, 10, 31),
        resident=resident
    )

    tax = PayeTax().calculate(context).tax_amount.amount

    assert Decimal("0") <= tax <= income


# Check that increasing income does not reduce PAYE for the same residency.
@settings(max_examples=100, derandomize=True)
@given(
    first=income_values,
    second=income_values,
    resident=st.booleans()
)
def test_paye_is_monotonic(
    first: Decimal,
    second: Decimal,
    resident: bool
) -> None:
    """Higher income must produce at least as much tax."""
    lower_income, higher_income = sorted((first, second))
    calculator = PayeTax()

    lower_tax = calculator.calculate(
        TaxContext(
            income=Money(lower_income),
            tax_date=date(2026, 10, 31),
            resident=resident
        )
    ).tax_amount.amount

    higher_tax = calculator.calculate(
        TaxContext(
            income=Money(higher_income),
            tax_date=date(2026, 10, 31),
            resident=resident
        )
    ).tax_amount.amount

    assert lower_tax <= higher_tax

# Check payroll deductions and confirm that all amounts reconcile.
def test_payroll_calculation() -> None:
    """Verify the example payroll and the separation of employer costs."""
    employee = TaxContext(
        income=Money("1500000"),
        allowances=Money("150000"),
        tax_date=date(2026, 10, 31),
        resident=True
    )

    result = Payroll(PayeTax()).calculate(
        employee,
        local_service_tax=Money("25000")
    )

    # Check independently calculated amounts for this example.
    assert result.gross_pay.amount == Decimal("1650000.00")
    assert result.employee_nssf.amount == Decimal("82500.00")
    assert result.employer_nssf.amount == Decimal("165000.00")
    assert result.chargeable_income.amount == Decimal("1625000.00")
    assert result.paye.amount == Decimal("375750.00")
    assert result.net_pay.amount == Decimal("1166750.00")
    assert result.employer_cost.amount == Decimal("1815000.00")

    # Employee deductions and net pay must add back to gross pay.
    assert (
        result.net_pay.amount
        + result.employee_nssf.amount
        + result.local_service_tax.amount
        + result.paye.amount
    ) == result.gross_pay.amount

    # Employer NSSF is added to gross pay, not deducted from net pay.
    assert result.employer_cost.amount == (
        result.gross_pay.amount + result.employer_nssf.amount
    )

 # Calculate payroll using the PAYE calculator.
    result = Payroll(PayeTax()).calculate(
        employee,
        local_service_tax=Money("25000")
    )
# Check that ineligible purchase VAT does not reduce VAT payable.
def test_vat_excludes_ineligible_input() -> None:
    """Recover only eligible input VAT from a mixture of invoices."""
    invoices = [
        Invoice("S-001", Money("1000000"), "sale", "standard"),
        Invoice("S-002", Money("500000"), "sale", "zero"),
        Invoice("S-003", Money("300000"), "sale", "exempt"),
        Invoice("P-001", Money("400000"), "purchase", "standard", True),
        Invoice("P-002", Money("100000"), "purchase", "standard", False)
    ]

    context = TaxContext(
        income=Money("0"),
        tax_date=date(2026, 10, 31),
        invoices=invoices
    )
    result = VatTax().calculate(context)

    assert result.taxable_amount.amount == Decimal("1500000.00")
    assert result.output_vat.amount == Decimal("180000.00")
    assert result.input_vat_charged.amount == Decimal("90000.00")
    assert result.recoverable_input_vat.amount == Decimal("72000.00")
    assert result.tax_amount.amount == Decimal("108000.00")
    assert result.vat_payable.amount == Decimal("108000.00")
    assert result.credit_balance.amount == Decimal("0.00")


# Check that eligible purchases can create a credit against zero-rated sales.
def test_vat_excess_input_credit() -> None:
    """Show excess input VAT as a credit rather than negative VAT payable."""
    invoices = [
        Invoice("S-001", Money("500000"), "sale", "zero"),
        Invoice("P-001", Money("200000"), "purchase", "standard", True)
    ]

    context = TaxContext(
        income=Money("0"),
        tax_date=date(2026, 10, 31),
        invoices=invoices
    )
    result = VatTax().calculate(context)

    assert result.output_vat.amount == Decimal("0.00")
    assert result.recoverable_input_vat.amount == Decimal("36000.00")
    assert result.tax_amount.amount == Decimal("-36000.00")
    assert result.vat_payable.amount == Decimal("0.00")
    assert result.credit_balance.amount == Decimal("36000.00")

# Check corporate tax for profitable and loss-making examples.
@pytest.mark.parametrize(
    "revenue, deductions, expected_income, expected_tax",
    [
        ("250000000", "175000000", "75000000.00", "22500000.00"),
        ("250000000", "280000000", "0.00", "0.00")
    ]
)
def test_corporate_tax(
    revenue: str,
    deductions: str,
    expected_income: str,
    expected_tax: str
) -> None:
    """Tax positive chargeable income without creating negative tax on a loss."""
    context = TaxContext(
        income=Money(revenue),
        deductions=Money(deductions),
        tax_date=date(2027, 6, 30),
        resident=True
    )

    result = CorporateTax().calculate(context)

    assert result.taxable_amount.amount == Decimal(expected_income)
    assert result.tax_amount.amount == Decimal(expected_tax)

# Check the financial differences between the two salary offers.
def test_salary_offer_comparison() -> None:
    """Verify the planner's proposed-minus-current calculations."""
    current = TaxContext(
        income=Money("1500000"),
        allowances=Money("150000"),
        tax_date=date(2026, 10, 31),
        resident=True
    )
    proposed = TaxContext(
        income=Money("1800000"),
        allowances=Money("150000"),
        tax_date=date(2026, 10, 31),
        resident=True
    )

    planner = TaxPlanner(Payroll(PayeTax()))
    result = planner.compare(
        current=current,
        proposed=proposed,
        current_lst=Money("25000"),
        proposed_lst=Money("25000")
    )

    # Check the independently calculated changes.
    assert result.gross_pay_change.amount == Decimal("300000.00")
    assert result.paye_change.amount == Decimal("90000.00")
    assert result.employee_nssf_change.amount == Decimal("15000.00")
    assert result.net_pay_change.amount == Decimal("195000.00")
    assert result.employer_cost_change.amount == Decimal("330000.00")

# Verify that an intentionally invalid float input raises TaxError.
def test_money_rejects_float() -> None:
    """Reject float inputs rather than silently converting them."""
    with pytest.raises(TaxError, match="string, integer or Decimal"):
        Money(0.1)  # pyright: ignore[reportArgumentType]


# Check that negative income is rejected when creating a context.
def test_negative_income_rejected() -> None:
    """Prevent negative income from reaching a tax calculator."""
    with pytest.raises(InvalidIncomeError, match="income cannot be negative"):
        TaxContext(
            income=Money("-100"),
            tax_date=date(2026, 10, 31)
        )

# Check dates on both sides of the supported PAYE period.
@pytest.mark.parametrize(
    "unsupported_date",
    [date(2026, 6, 30), date(2027, 7, 1)]
)
def test_unsupported_paye_date(unsupported_date: date) -> None:
    """Reject dates for which no PAYE schedule has been implemented."""
    context = TaxContext(
        income=Money("1500000"),
        tax_date=unsupported_date
    )

    with pytest.raises(NoScheduleForDateError):
        PayeTax().calculate(context)