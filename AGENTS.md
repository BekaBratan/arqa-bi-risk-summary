# Working instructions

Use PostgreSQL SQL as the source of dashboard numbers. Keep money as NUMERIC until JSON export.
Grain is one loan per report date. Remove exact duplicates only and fail on conflicting versions.
Exclude written-off loans. Match FX on the exact date. KZT is always 1.
NPL is DPD > 90 OR restructured. Apply its 50% provision before other DPD bands.
Calculate ratios from summed amounts, never average loan or sector ratios.
Rank groups separately on each date, with group_id as the tie breaker.
Check SQL against an independent Decimal calculation and boundary fixtures.
Report actual AI mistakes honestly. Do not invent candidate experience or manual corrections.
