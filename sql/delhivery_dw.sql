-- Primary Keys
ALTER TABLE dim_center ADD PRIMARY KEY (center_id);
ALTER TABLE dim_route_type ADD PRIMARY KEY (route_type_id);
ALTER TABLE dim_date ADD PRIMARY KEY (date_id);

-- Foreign Keys on fact_trips
ALTER TABLE fact_trips 
    ADD CONSTRAINT fk_source_center FOREIGN KEY (source_center_id) REFERENCES dim_center(center_id);

ALTER TABLE fact_trips 
    ADD CONSTRAINT fk_destination_center FOREIGN KEY (destination_center_id) REFERENCES dim_center(center_id);

ALTER TABLE fact_trips 
    ADD CONSTRAINT fk_route_type FOREIGN KEY (route_type_id) REFERENCES dim_route_type(route_type_id);

ALTER TABLE fact_trips 
    ADD CONSTRAINT fk_date FOREIGN KEY (date_id) REFERENCES dim_date(date_id);
-- ---------------------------------------------------------------------------------------------------------
-- Views
--Corridor Performance
CREATE VIEW corridor_performance AS
SELECT 
    ft.corridor_id,
    COUNT(*) AS total_trips,
    ROUND(AVG(ft.delay_percentage)::numeric, 2) AS avg_delay_pct,
    SUM(ft.delay_flag) AS delayed_trips,
    ROUND(SUM(ft.delay_flag)::numeric / COUNT(*) * 100, 2) AS delay_rate_pct,
    ROUND(AVG(ft.actual_time)::numeric, 2) AS avg_actual_time,
    ROUND(AVG(ft.osrm_time)::numeric, 2) AS avg_osrm_time
FROM fact_trips ft
GROUP BY ft.corridor_id
HAVING COUNT(*) >= 5
ORDER BY avg_delay_pct DESC;

-- Hub Performance (source center wise)
CREATE VIEW hub_performance AS
SELECT 
    dc.center_name,
    dc.city,
    dc.state,
    COUNT(*) AS total_trips,
    ROUND(AVG(ft.delay_percentage)::numeric, 2) AS avg_delay_pct,
    SUM(ft.delay_flag) AS delayed_trips,
    ROUND(SUM(ft.delay_flag)::numeric / COUNT(*) * 100, 2) AS delay_rate_pct
FROM fact_trips ft
JOIN dim_center dc ON ft.source_center_id = dc.center_id
GROUP BY dc.center_name, dc.city, dc.state
HAVING COUNT(*) >= 5
ORDER BY avg_delay_pct DESC;

-- Route Type Comparison (FTL vs Carting)
CREATE VIEW route_type_performance AS
SELECT 
    drt.route_type,
    COUNT(*) AS total_trips,
    ROUND(AVG(ft.delay_percentage)::numeric, 2) AS avg_delay_pct,
    ROUND(SUM(ft.delay_flag)::numeric / COUNT(*) * 100, 2) AS delay_rate_pct,
    ROUND(AVG(ft.route_efficiency)::numeric, 3) AS avg_route_efficiency,
    ROUND(AVG(ft.time_efficiency)::numeric, 3) AS avg_time_efficiency
FROM fact_trips ft
JOIN dim_route_type drt ON ft.route_type_id = drt.route_type_id
GROUP BY drt.route_type
ORDER BY avg_delay_pct DESC;


-- Time-based Performance (day of week / weekend)
CREATE VIEW time_based_performance AS
SELECT 
    dd.day_name,
    dd.is_weekend,
    COUNT(*) AS total_trips,
    ROUND(AVG(ft.delay_percentage)::numeric, 2) AS avg_delay_pct,
    ROUND(SUM(ft.delay_flag)::numeric / COUNT(*) * 100, 2) AS delay_rate_pct
FROM fact_trips ft
JOIN dim_date dd ON ft.date_id = dd.date_id
GROUP BY dd.day_name, dd.is_weekend
ORDER BY avg_delay_pct DESC;

-- Interstate vs Intrastate
CREATE VIEW interstate_performance AS
SELECT 
    ft.is_interstate,
    COUNT(*) AS total_trips,
    ROUND(AVG(ft.delay_percentage)::numeric, 2) AS avg_delay_pct,
    ROUND(SUM(ft.delay_flag)::numeric / COUNT(*) * 100, 2) AS delay_rate_pct
FROM fact_trips ft
GROUP BY ft.is_interstate;
-- -----------------------------------------------------------------------------------

SELECT table_name FROM information_schema.views WHERE table_schema = 'public';
SELECT * FROM corridor_performance LIMIT 10;
-- -----------------------------------------------------------------------------------


-- Analytical Queries
-- Corridor Risk Ranking
SELECT 
    corridor_id,
    total_trips,
    avg_delay_pct,
    RANK() OVER (ORDER BY avg_delay_pct DESC) AS risk_rank
FROM corridor_performance
LIMIT 15;

-- Top 3 Worst Hubs per State
SELECT * FROM (
    SELECT 
        state,
        center_name,
        avg_delay_pct,
        ROW_NUMBER() OVER (PARTITION BY state ORDER BY avg_delay_pct DESC) AS rn
    FROM hub_performance
) ranked
WHERE rn <= 3;


-- States with Above-Average Delay
WITH state_avg AS (
    SELECT 
        dc.state,
        AVG(ft.delay_percentage) AS avg_delay
    FROM fact_trips ft
    JOIN dim_center dc ON ft.source_center_id = dc.center_id
    GROUP BY dc.state
),
overall_avg AS (
    SELECT AVG(delay_percentage) AS overall_delay FROM fact_trips
)
SELECT s.state, ROUND(s.avg_delay::numeric, 2) AS state_avg_delay
FROM state_avg s, overall_avg o
WHERE s.avg_delay > o.overall_delay
ORDER BY s.avg_delay DESC;