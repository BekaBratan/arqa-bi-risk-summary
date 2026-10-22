CREATE OR REPLACE VIEW reporting.v_portfolio_clean AS
WITH dedup AS (
    SELECT DISTINCT * FROM raw.portfolio
), fx AS (
    SELECT DISTINCT * FROM raw.fx
), converted AS (
    SELECT p.*, CASE WHEN p.currency = 'KZT' THEN 1::numeric ELSE f.rate_kzt END AS rate_kzt,
           p.principal_outstanding *
               CASE WHEN p.currency = 'KZT' THEN 1::numeric ELSE f.rate_kzt END AS outstanding_kzt,
           (p.days_past_due > 90 OR p.restructured = 1) AS is_npl
    FROM dedup p
    LEFT JOIN fx f ON f.date = p.report_date AND f.currency = p.currency
    WHERE p.written_off = 0
), classified AS (
    SELECT *, CASE WHEN is_npl THEN 0.50::numeric
                   WHEN days_past_due > 30 THEN 0.10::numeric
                   ELSE 0.01::numeric END AS provision_rate
    FROM converted
)
SELECT *, CASE WHEN days_past_due > 30 THEN outstanding_kzt ELSE 0 END AS par30_kzt,
          CASE WHEN days_past_due > 90 THEN outstanding_kzt ELSE 0 END AS par90_kzt,
          CASE WHEN is_npl THEN outstanding_kzt ELSE 0 END AS npl_kzt,
          outstanding_kzt * provision_rate AS provisions_kzt
FROM classified;

CREATE OR REPLACE VIEW reporting.v_group_exposure AS
WITH groups AS (
    SELECT report_date, group_id, sum(outstanding_kzt) AS outstanding_kzt
    FROM reporting.v_portfolio_clean
    GROUP BY report_date, group_id
)
SELECT *, row_number() OVER (
    PARTITION BY report_date ORDER BY outstanding_kzt DESC, group_id
) AS exposure_rank
FROM groups;

CREATE OR REPLACE VIEW reporting.v_metrics AS
WITH totals AS (
    SELECT report_date, count(*) AS loan_count,
           sum(outstanding_kzt) AS portfolio_kzt,
           sum(par30_kzt) AS par30_kzt, sum(par90_kzt) AS par90_kzt,
           sum(npl_kzt) AS npl_kzt, sum(provisions_kzt) AS provisions_kzt
    FROM reporting.v_portfolio_clean GROUP BY report_date
), concentration AS (
    SELECT report_date, sum(outstanding_kzt) FILTER (WHERE exposure_rank <= 10) AS top10_kzt
    FROM reporting.v_group_exposure GROUP BY report_date
)
SELECT t.*, c.top10_kzt,
       par30_kzt / nullif(portfolio_kzt, 0) AS par30_ratio,
       par90_kzt / nullif(portfolio_kzt, 0) AS par90_ratio,
       npl_kzt / nullif(portfolio_kzt, 0) AS npl_ratio,
       provisions_kzt / nullif(portfolio_kzt, 0) AS provision_ratio,
       top10_kzt / nullif(portfolio_kzt, 0) AS top10_ratio
FROM totals t JOIN concentration c USING (report_date);

CREATE OR REPLACE VIEW reporting.v_metrics_change AS
SELECT m.*,
       m.portfolio_kzt - b.portfolio_kzt AS portfolio_change_kzt,
       m.portfolio_kzt / nullif(b.portfolio_kzt, 0) - 1 AS portfolio_change_ratio,
       m.provisions_kzt - b.provisions_kzt AS provisions_change_kzt,
       m.provisions_kzt / nullif(b.provisions_kzt, 0) - 1 AS provisions_change_ratio,
       (m.par30_ratio - b.par30_ratio) * 100 AS par30_change_pp,
       (m.par90_ratio - b.par90_ratio) * 100 AS par90_change_pp,
       (m.npl_ratio - b.npl_ratio) * 100 AS npl_change_pp,
       (m.provision_ratio - b.provision_ratio) * 100 AS provision_change_pp,
       (m.top10_ratio - b.top10_ratio) * 100 AS top10_change_pp
FROM reporting.v_metrics m
CROSS JOIN (SELECT * FROM reporting.v_metrics WHERE report_date = DATE '2026-09-01') b;

CREATE OR REPLACE VIEW reporting.v_segments AS
WITH segments AS (
    SELECT report_date, 'sector'::text AS dimension, sector AS segment,
           sum(outstanding_kzt) AS portfolio_kzt, sum(npl_kzt) AS npl_kzt,
           sum(par30_kzt) AS par30_kzt, sum(par90_kzt) AS par90_kzt,
           sum(provisions_kzt) AS provisions_kzt
    FROM reporting.v_portfolio_clean GROUP BY report_date, sector
    UNION ALL
    SELECT report_date, 'program', program,
           sum(outstanding_kzt), sum(npl_kzt), sum(par30_kzt), sum(par90_kzt), sum(provisions_kzt)
    FROM reporting.v_portfolio_clean GROUP BY report_date, program
)
SELECT *, npl_kzt / nullif(portfolio_kzt, 0) AS npl_ratio FROM segments;

CREATE OR REPLACE VIEW reporting.v_quality AS
SELECT d.report_date, count(*) AS raw_rows,
       count(*) - count(DISTINCT d.loan_id) AS duplicate_rows,
       (SELECT count(*) FROM (SELECT DISTINCT * FROM raw.portfolio) p
        WHERE p.report_date = d.report_date AND p.written_off = 1) AS written_off_loans,
       (SELECT count(*) FROM reporting.v_portfolio_clean p
        WHERE p.report_date = d.report_date) AS included_loans
FROM raw.portfolio d GROUP BY d.report_date;
