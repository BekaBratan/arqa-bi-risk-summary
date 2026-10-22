BEGIN;
TRUNCATE raw.portfolio, raw.fx;
INSERT INTO raw.fx VALUES ('2026-09-01', 'USD', 500);
INSERT INTO raw.portfolio
SELECT DATE '2026-09-01', 'E' || n, 'B' || n,
       CASE WHEN n <= 2 THEN 'G01' ELSE 'G' || lpad(n::text,2,'0') END,
       'Test', 'Test', CASE WHEN n = 1 THEN 'USD' ELSE 'KZT' END,
       DATE '2025-01-01', DATE '2027-01-01',
       CASE WHEN n = 1 THEN 2 ELSE 1000 END,
       CASE n WHEN 1 THEN 30 WHEN 2 THEN 31 WHEN 3 THEN 90 WHEN 4 THEN 91 ELSE 0 END,
       CASE WHEN n = 5 THEN 1 ELSE 0 END, CASE WHEN n = 13 THEN 1 ELSE 0 END
FROM generate_series(1,13) n;
INSERT INTO raw.portfolio SELECT * FROM raw.portfolio WHERE loan_id = 'E1';
DO $$
DECLARE m record;
BEGIN
    SELECT * INTO m FROM reporting.v_metrics;
    IF m.loan_count <> 12 OR m.portfolio_kzt <> 12000 OR m.par30_kzt <> 3000
       OR m.par90_kzt <> 1000 OR m.npl_kzt <> 2000 OR m.provisions_kzt <> 1280
       OR m.top10_kzt <> 11000
    THEN RAISE EXCEPTION 'Boundary/FX/duplicate/write-off/group test failed: %', row_to_json(m); END IF;
    IF (SELECT provision_rate FROM reporting.v_portfolio_clean WHERE loan_id = 'E5') <> .5
    THEN RAISE EXCEPTION 'Restructuring must override low DPD'; END IF;
END $$;
DELETE FROM raw.fx;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM reporting.v_portfolio_clean WHERE rate_kzt IS NULL)
    THEN RAISE EXCEPTION 'Missing FX must remain visible'; END IF;
END $$;
ROLLBACK;
