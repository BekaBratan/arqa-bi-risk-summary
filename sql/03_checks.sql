DO $$
BEGIN
    IF EXISTS (
        SELECT report_date, loan_id FROM (SELECT DISTINCT * FROM raw.portfolio) p
        GROUP BY report_date, loan_id HAVING count(*) > 1
    ) THEN RAISE EXCEPTION 'Conflicting loan versions'; END IF;
    IF EXISTS (
        SELECT date, currency FROM (SELECT DISTINCT * FROM raw.fx) f
        GROUP BY date, currency HAVING count(*) > 1
    ) THEN RAISE EXCEPTION 'Conflicting FX rates'; END IF;
    IF EXISTS (SELECT 1 FROM raw.fx WHERE currency = 'KZT' AND rate_kzt <> 1)
    THEN RAISE EXCEPTION 'KZT rate must be 1'; END IF;
    IF EXISTS (SELECT 1 FROM reporting.v_portfolio_clean WHERE rate_kzt IS NULL)
    THEN RAISE EXCEPTION 'Missing exact-date FX rate'; END IF;
    IF EXISTS (SELECT 1 FROM raw.portfolio WHERE
        btrim(loan_id) = '' OR btrim(borrower_id) = '' OR btrim(group_id) = '' OR
        btrim(sector) = '' OR btrim(program) = '' OR currency NOT IN ('KZT','USD') OR
        issue_date > report_date OR maturity_date < issue_date)
    THEN RAISE EXCEPTION 'Invalid dimensions or dates'; END IF;
    IF (SELECT array_agg(DISTINCT report_date ORDER BY report_date) FROM raw.portfolio)
        IS DISTINCT FROM ARRAY[DATE '2026-09-01', DATE '2026-10-01']
    THEN RAISE EXCEPTION 'Expected both assignment snapshot dates'; END IF;
    IF EXISTS (SELECT 1 FROM reporting.v_metrics WHERE
        NOT (0 <= par90_ratio AND par90_ratio <= par30_ratio AND par30_ratio <= 1
             AND par90_ratio <= npl_ratio AND npl_ratio <= 1
             AND top10_ratio > 0 AND top10_ratio <= 1))
    THEN RAISE EXCEPTION 'Risk ratio invariant failed'; END IF;
END $$;
