CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE TABLE IF NOT EXISTS raw.portfolio (
    report_date date NOT NULL,
    loan_id text NOT NULL,
    borrower_id text NOT NULL,
    group_id text NOT NULL,
    sector text NOT NULL,
    program text NOT NULL,
    currency text NOT NULL,
    issue_date date NOT NULL,
    maturity_date date NOT NULL,
    principal_outstanding numeric NOT NULL CHECK (principal_outstanding >= 0),
    days_past_due integer NOT NULL CHECK (days_past_due >= 0),
    restructured integer NOT NULL CHECK (restructured IN (0, 1)),
    written_off integer NOT NULL CHECK (written_off IN (0, 1))
);

CREATE TABLE IF NOT EXISTS raw.fx (
    date date NOT NULL,
    currency text NOT NULL,
    rate_kzt numeric NOT NULL CHECK (rate_kzt > 0)
);
