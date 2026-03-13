# Payroll Module

## Overview
The `payroll` app is responsible for defining salary structures, calculating earnings and deductions, and generating payslips.

## File Breakdown

### `models.py`
- **`SalaryStructure`**: Defines the components of an employee's salary (Basic, HRA, Allowances, etc.).
- **`Payslip`**: Stores the results of a payroll run for an individual employee, including net pay and tax calculations.
- **`Deduction`**: Defines taxes, insurance, or other subtractions from the gross pay.

### `services.py`
- **Logic**: The "Engine" of the payroll app. It iterates through employees, applies salary structures, calculates time-based earnings (linked to `attendance`), and computes final totals.

### `tasks.py`
- **Logic**: Celery tasks for bulk processing payroll at the end of the month.

### `graphql/` (Directory)
- **`queries.py`**: Fetching personal payslips and payroll summaries.
- **`mutations.py`**: Initiating payroll runs (for HR/Admin) and updating salary structures.

## Key Logic
- **Integration**: Heavily dependent on the `attendance` app for calculating "loss of pay" (LOP) and the `leaves` app for paid/unpaid leave context.
- **Precision**: Calculations are performed with high decimal precision to ensure financial accuracy.
