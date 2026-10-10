"""Reusable money, payroll and tax calculations for the Uganda tax project."""

# Import tools for defining a common interface for tax calculators.
from abc import ABC, abstractmethod

# Import tools for structured calculation inputs and calendar dates.
from dataclasses import dataclass, field
from datetime import date

# Import decimal arithmetic tools and an explicit rounding rule.
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Define the parent exception for errors raised by our tax engine.
class TaxError(Exception):
    """Represent a tax calculation or configuration error."""


# Identify income values that cannot be used in a calculation.
class InvalidIncomeError(TaxError):
    """Represent invalid income, such as a negative or non-finite amount."""


# Identify dates for which the engine has no supported tax schedule.
class NoScheduleForDateError(TaxError):
    """Represent a calculation date without a supported tax schedule."""

# Represent a UGX amount using decimal arithmetic and explicit rounding.
class Money:
    """Store UGX to two decimal places, rounding halfway values upward."""

    def __init__(self, amount: str | int | Decimal) -> None:
        """Create a monetary amount from an exact input type."""

        # Reject floats and booleans rather than silently converting them.
        if isinstance(amount, bool) or not isinstance(
            amount, (str, int, Decimal)
        ):
            raise TaxError("Money requires a string, integer or Decimal.")

        try:
            # Convert the input and reject infinity or undefined values.
            value = Decimal(amount)

            if not value.is_finite():
                raise TaxError("Money must be a finite amount.")

            # Apply the project's two-decimal-place rounding convention.
            self.amount = value.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

        except InvalidOperation as error:
            raise TaxError("Invalid or unsupported monetary amount.") from error

    # Provide a readable representation when the object is displayed.
    def __repr__(self) -> str:
        """Display the currency and amount with thousands separators."""
        return f"UGX {self.amount:,.2f}"
    # Add two monetary amounts and return a new Money object.
    def __add__(self, other: "Money") -> "Money":
        """Combine two UGX amounts."""
        if not isinstance(other, Money):
            return NotImplemented

        return Money(self.amount + other.amount)

    # Multiply an amount by an exact decimal rate or integer.
    def __mul__(self, factor: Decimal | int) -> "Money":
        """Scale a UGX amount using the project's rounding convention."""
        if isinstance(factor, bool) or not isinstance(factor, (Decimal, int)):
            return NotImplemented

        return Money(self.amount * Decimal(factor))

    # Compare two monetary amounts using the less-than operator.
    def __lt__(self, other: "Money") -> bool:
        """Check whether this amount is smaller than another."""
        if not isinstance(other, Money):
            return NotImplemented

        return self.amount < other.amount

# Group the inputs needed by our tax calculators.
@dataclass
class TaxContext:
    """Hold income, adjustments, residency and the calculation date."""

    income: Money
    tax_date: date
    resident: bool = True
    allowances: Money = field(default_factory=lambda: Money("0"))
    deductions: Money = field(default_factory=lambda: Money("0"))

    # Store a separate invoice list for each calculation context.
    invoices: list["Invoice"] = field(default_factory=list)

    # Validate inputs immediately after the context is created.
    def __post_init__(self) -> None:
        """Reject invalid amounts, dates and residency indicators."""
        for name in ("income", "allowances", "deductions"):
            value = getattr(self, name)

            if not isinstance(value, Money):
                raise InvalidIncomeError(f"{name} must be a Money object.")

            if value.amount < Decimal("0"):
                raise InvalidIncomeError(f"{name} cannot be negative.")

        if type(self.tax_date) is not date:
            raise TaxError("tax_date must be a date object.")

        if type(self.resident) is not bool:
            raise TaxError("resident must be True or False.")

# Store a tax calculation's name, taxable amount and resulting tax.
@dataclass
class TaxResult:
    """Present the main outputs of a tax calculation."""

    tax_name: str
    taxable_amount: Money
    tax_amount: Money


# Require every tax calculator to provide the same calculation method.
class Tax(ABC):
    """Define the interface shared by concrete tax calculators."""

    # Let each subclass implement its own calculation rules.
    @abstractmethod
    def calculate(self, ctx: TaxContext) -> TaxResult:
        """Calculate tax from the supplied context."""
        pass

# Calculate monthly PAYE using the supported resident or non-resident schedule.
class PayeTax(Tax):
    """Calculate monthly PAYE for the project's 2026/27 schedule."""

    # Apply progressive bands to chargeable employment income.
    def calculate(self, ctx: TaxContext) -> TaxResult:
        """Return PAYE after adding allowances and permitted deductions."""

        # Reject dates outside the period supported by this implementation.
        if not date(2026, 7, 1) <= ctx.tax_date <= date(2027, 6, 30):
            raise NoScheduleForDateError(
                "PAYE is supported from 1 July 2026 to 30 June 2027."
            )

        # Treat supplied allowances as taxable and deductions as permitted.
        gross_income = ctx.income.amount + ctx.allowances.amount

        if ctx.deductions.amount > gross_income:
            raise InvalidIncomeError("Deductions cannot exceed gross income.")

        chargeable = gross_income - ctx.deductions.amount

        # Calculate resident PAYE before the additional high-income charge.
        if ctx.resident:
            if chargeable <= Decimal("335000"):
                tax = Decimal("0")
            elif chargeable <= Decimal("410000"):
                tax = (chargeable - Decimal("335000")) * Decimal("0.20")
            elif chargeable <= Decimal("485000"):
                tax = (
                    Decimal("15000")
                    + (chargeable - Decimal("410000")) * Decimal("0.25")
                )
            else:
                tax = (
                    Decimal("33750")
                    + (chargeable - Decimal("485000")) * Decimal("0.30")
                )

        # Non-residents have a separate schedule without a tax-free band.
        else:
            if chargeable <= Decimal("335000"):
                tax = chargeable * Decimal("0.10")
            elif chargeable <= Decimal("410000"):
                tax = (
                    Decimal("33500")
                    + (chargeable - Decimal("335000")) * Decimal("0.20")
                )
            else:
                tax = (
                    Decimal("48500")
                    + (chargeable - Decimal("410000")) * Decimal("0.30")
                )

        # Apply the additional 10% only to income above UGX 10 million.
        if chargeable > Decimal("10000000"):
            tax += (chargeable - Decimal("10000000")) * Decimal("0.10")

        # Round the final tax through Money and return a structured result.
        return TaxResult(
            tax_name="PAYE",
            taxable_amount=Money(chargeable),
            tax_amount=Money(tax)
        )


# Store the employee deductions and employer cost in one payroll result.
@dataclass
class PayrollResult:
    """Present the amounts calculated for one employee's monthly payroll."""

    gross_pay: Money
    employee_nssf: Money
    employer_nssf: Money
    local_service_tax: Money
    chargeable_income: Money
    paye: Money
    net_pay: Money
    employer_cost: Money

# Combine NSSF, Local Service Tax and PAYE into a monthly payroll calculation.
class Payroll:
    """Calculate payroll for an employee covered by NSSF."""

    # Reuse a PAYE calculator through composition.
    def __init__(self, paye_calculator: PayeTax) -> None:
        """Store the calculator used to determine PAYE."""
        self.paye_calculator = paye_calculator

    # Calculate employee take-home pay and the employer's total cost.
    def calculate(
        self,
        ctx: TaxContext,
        local_service_tax: Money
    ) -> PayrollResult:
        """Apply NSSF and the supplied monthly LST deduction."""

        # Accept LST explicitly and prevent duplicate or unrelated deductions.
        if not isinstance(local_service_tax, Money):
            raise TaxError("Local Service Tax must be a Money object.")

        if local_service_tax.amount < Decimal("0"):
            raise TaxError("Local Service Tax cannot be negative.")

        if ctx.deductions.amount != Decimal("0"):
            raise TaxError(
                "Keep context deductions at zero; supply LST separately."
            )

        # Calculate both NSSF contributions from gross monthly pay.
        gross_pay = ctx.income + ctx.allowances
        employee_nssf = gross_pay * Decimal("0.05")
        employer_nssf = gross_pay * Decimal("0.10")

        # Reduce PAYE income by LST, without deducting employee NSSF.
        paye_context = TaxContext(
            income=ctx.income,
            allowances=ctx.allowances,
            deductions=local_service_tax,
            tax_date=ctx.tax_date,
            resident=ctx.resident
        )
        paye_result = self.paye_calculator.calculate(paye_context)

        # Subtract employee deductions to obtain take-home pay.
        net_amount = (
            gross_pay.amount
            - employee_nssf.amount
            - local_service_tax.amount
            - paye_result.tax_amount.amount
        )

        if net_amount < Decimal("0"):
            raise TaxError("The supplied deductions would produce negative net pay.")

        # Employer NSSF increases employer cost, not employee deductions.
        return PayrollResult(
            gross_pay=gross_pay,
            employee_nssf=employee_nssf,
            employer_nssf=employer_nssf,
            local_service_tax=local_service_tax,
            chargeable_income=paye_result.taxable_amount,
            paye=paye_result.tax_amount,
            net_pay=Money(net_amount),
            employer_cost=gross_pay + employer_nssf
        )

# Represent one sale or purchase with its VAT treatment.
@dataclass
class Invoice:
    """Store a VAT-exclusive amount and its classification."""

    reference: str
    amount: Money
    transaction: str
    category: str
    input_vat_eligible: bool = False

    # Reject invalid invoice details before calculating VAT.
    def __post_init__(self) -> None:
        """Validate the invoice amount, type and eligibility flag."""
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise TaxError("An invoice reference is required.")

        if not isinstance(self.amount, Money):
            raise TaxError("The invoice amount must be a Money object.")

        if self.amount.amount < Decimal("0"):
            raise TaxError("Invoice amounts cannot be negative.")

        if self.transaction not in ("sale", "purchase"):
            raise TaxError("Transaction must be 'sale' or 'purchase'.")

        if self.category not in ("standard", "zero", "exempt"):
            raise TaxError("Category must be 'standard', 'zero' or 'exempt'.")

        if type(self.input_vat_eligible) is not bool:
            raise TaxError("Input VAT eligibility must be True or False.")

        # Only standard-rated purchases can carry recoverable VAT here.
        if self.input_vat_eligible and (
            self.transaction != "purchase" or self.category != "standard"
        ):
            raise TaxError(
                "Input VAT eligibility applies only to standard-rated purchases."
            )

    # Calculate the VAT charged on this invoice.
    def vat_amount(self) -> Money:
        """Apply 18% to standard-rated amounts and zero to other categories."""
        if self.category == "standard":
            return self.amount * Decimal("0.18")

        return Money("0")

# Extend the common tax result with the details needed for VAT reporting.
@dataclass
class VatResult(TaxResult):
    """Separate output VAT, purchase VAT, recoverable credit and payment."""

    output_vat: Money
    input_vat_charged: Money
    recoverable_input_vat: Money
    vat_payable: Money
    credit_balance: Money

# Calculate VAT from the sales and purchases supplied in a tax context.
class VatTax(Tax):
    """Calculate VAT using classified invoices and explicit input eligibility."""

    # Summarise output VAT, purchase VAT and recoverable input credits.
    def calculate(self, ctx: TaxContext) -> VatResult:
        """Return the net VAT balance and its payable or credit portion."""

        # Restrict calculations to the project's supported period.
        if not date(2026, 7, 1) <= ctx.tax_date <= date(2027, 6, 30):
            raise NoScheduleForDateError(
                "VAT is supported from 1 July 2026 to 30 June 2027."
            )

        # VAT uses invoices rather than the income adjustment fields.
        if any(
            value.amount != Decimal("0")
            for value in (ctx.income, ctx.allowances, ctx.deductions)
        ):
            raise TaxError("For VAT, supply invoices and keep income fields at zero.")

        if not isinstance(ctx.invoices, list):
            raise TaxError("Invoices must be supplied as a list.")

        # Accumulate monetary values using Decimal only.
        taxable_sales = Decimal("0")
        output_vat = Decimal("0")
        input_vat = Decimal("0")
        recoverable_vat = Decimal("0")
        references = set()

        for invoice in ctx.invoices:
            if not isinstance(invoice, Invoice):
                raise TaxError("Every invoice must be an Invoice object.")

            # Prevent duplicate entries within sales or purchases.
            invoice_key = (invoice.transaction, invoice.reference)
            if invoice_key in references:
                raise TaxError(f"Duplicate invoice: {invoice.reference}.")
            references.add(invoice_key)

            vat = invoice.vat_amount().amount

            # Include zero-rated sales in taxable turnover, but not exempt sales.
            if invoice.transaction == "sale":
                output_vat += vat
                if invoice.category != "exempt":
                    taxable_sales += invoice.amount.amount

            # Separate VAT charged on purchases from the recoverable portion.
            else:
                input_vat += vat
                if invoice.input_vat_eligible:
                    recoverable_vat += vat

        # Separate a positive payment obligation from an excess input credit.
        net_vat = output_vat - recoverable_vat
        zero = Decimal("0")

        return VatResult(
            tax_name="VAT",
            taxable_amount=Money(taxable_sales),
            tax_amount=Money(net_vat),
            output_vat=Money(output_vat),
            input_vat_charged=Money(input_vat),
            recoverable_input_vat=Money(recoverable_vat),
            vat_payable=Money(max(net_vat, zero)),
            credit_balance=Money(max(-net_vat, zero))
        )

# Calculate standard corporate income tax for a resident company.
class CorporateTax(Tax):
    """Apply 30% to positive annual income after allowable deductions."""

    # Calculate the annual liability before payments and tax credits.
    def calculate(self, ctx: TaxContext) -> TaxResult:
        """Calculate tax from revenue and pre-validated allowable deductions."""

        # Restrict calculations to the project's supported schedule period.
        if not date(2026, 7, 1) <= ctx.tax_date <= date(2027, 6, 30):
            raise NoScheduleForDateError(
                "Corporate tax is supported from 1 July 2026 to 30 June 2027."
            )

        # Keep this simplified calculator within its documented scope.
        if not ctx.resident:
            raise TaxError("This corporate calculator supports resident companies.")

        if ctx.allowances.amount != Decimal("0") or ctx.invoices:
            raise TaxError(
                "For corporate tax, use income and deductions only."
            )

        # Treat income as annual revenue and deductions as allowable expenses.
        income_after_deductions = ctx.income.amount - ctx.deductions.amount

        # A loss produces no current tax in this simplified model.
        chargeable = max(income_after_deductions, Decimal("0"))
        tax = chargeable * Decimal("0.30")

        # Return the taxable amount and rounded annual tax liability.
        return TaxResult(
            tax_name="Corporate income tax",
            taxable_amount=Money(chargeable),
            tax_amount=Money(tax)
        )

# Store two payroll results and the financial differences between them.
@dataclass
class TaxComparison:
    """Compare a proposed offer with the current offer."""

    current: PayrollResult
    proposed: PayrollResult
    gross_pay_change: Money
    paye_change: Money
    employee_nssf_change: Money
    net_pay_change: Money
    employer_cost_change: Money

# Compare salary offers by reusing the payroll calculator.
class TaxPlanner:
    """Compare two payroll scenarios for the same date and residency."""

    # Store the payroll calculator through composition.
    def __init__(self, payroll: Payroll) -> None:
        """Receive the calculator used for both scenarios."""
        self.payroll = payroll

    # Calculate both offers and report proposed-minus-current differences.
    def compare(
        self,
        current: TaxContext,
        proposed: TaxContext,
        current_lst: Money,
        proposed_lst: Money
    ) -> TaxComparison:
        """Compare two offers using explicitly supplied LST deductions."""

        # Keep the comparison focused on offers under the same conditions.
        if current.tax_date != proposed.tax_date:
            raise TaxError("Both scenarios must use the same calculation date.")

        if current.resident != proposed.resident:
            raise TaxError("Both scenarios must use the same residency status.")

        # Apply the existing payroll rules to each scenario.
        current_result = self.payroll.calculate(current, current_lst)
        proposed_result = self.payroll.calculate(proposed, proposed_lst)

        # Calculate differences using Decimal amounts.
        return TaxComparison(
            current=current_result,
            proposed=proposed_result,
            gross_pay_change=Money(
                proposed_result.gross_pay.amount - current_result.gross_pay.amount
            ),
            paye_change=Money(
                proposed_result.paye.amount - current_result.paye.amount
            ),
            employee_nssf_change=Money(
                proposed_result.employee_nssf.amount
                - current_result.employee_nssf.amount
            ),
            net_pay_change=Money(
                proposed_result.net_pay.amount - current_result.net_pay.amount
            ),
            employer_cost_change=Money(
                proposed_result.employer_cost.amount
                - current_result.employer_cost.amount
            )
        )