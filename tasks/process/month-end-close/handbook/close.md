# Month-end close (CLS)

Close entries are dated the last day of the month being closed. The source documents arrive in the accounting
inbox; use the latest one for each item.

**CLS-1.1** Depreciation. Book the month's depreciation from the fixed asset register: debit 6550 Depreciation
(department PROD), credit 1550 Accumulated depreciation, for the register's total monthly charge. An asset
starts depreciating in the month after it is placed in service.

**CLS-1.2** Prepaid insurance. Amortize prepaid insurance from the insurance schedule: debit 6450 Insurance
(department ADMIN), credit 1400 Prepaid expenses, for the monthly charge of the policy in force that month.

**CLS-1.3** Unpaid wages. Accrue wages earned in the month but paid in the next one, from the payroll provider's
report: debit 6000 Wages and salaries and 6050 Payroll taxes and benefits (department of the employees), credit
2150 Accrued payroll.

**CLS-1.4** Unbilled services. Accrue services used in the month whose bill has not arrived, from the best
evidence available (a meter reading, a quote, a contract): debit the expense account and department the bill
will be coded to, credit 2100 Accrued liabilities.

**CLS-2.1** When every close entry is posted, run the control-ties report and confirm each control account ties
to its subledger before telling the controller the books are ready.
