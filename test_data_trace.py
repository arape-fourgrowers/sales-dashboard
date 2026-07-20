#!/usr/bin/env python3
"""
Test script to trace data flow and verify calculations
"""
import pandas as pd
import pg8000.native
from datetime import datetime

# Database configuration
DB_HOST = 'fourgrowers-analytics-db.clswl6o06h7g.us-east-2.rds.amazonaws.com'
DB_NAME = 'postgres'
DB_PASS = 'FourGrowers2026!'
DB_USER = 'analyticsuser'

print("="*80)
print("DATA FLOW TRACE")
print("="*80)

# Test Fruit Analytics query
print("\n1. FRUIT ANALYTICS (Database)")
print("-" * 80)

try:
    conn = pg8000.native.Connection(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        database=DB_NAME,
        timeout=60
    )
    
    query = """
    SELECT
        DATE("timestamp") AS harvest_date,
        COUNT(*) FILTER (WHERE ("data"->>'Ripeness')::float >= 4) AS ripe_count,
        MAX(("data"->>'x (m)')::float) AS max_distance,
        COUNT(DISTINCT "timestamp") AS num_harvests
    FROM farm_events
    WHERE farm_id = 'costa'
        AND event_type = 'harvest'
        AND "timestamp" >= CURRENT_DATE - INTERVAL '10 days'
        AND ("data"->>'Ripeness') IS NOT NULL
        AND ("data"->>'x (m)') IS NOT NULL
    GROUP BY DATE("timestamp")
    HAVING MAX(("data"->>'x (m)')::float) > 0
    ORDER BY harvest_date DESC
    LIMIT 5
    """
    
    conn.run("SET statement_timeout = 30000")
    result = conn.run(query)
    conn.close()
    
    if result:
        df = pd.DataFrame(result, columns=['harvest_date', 'ripe_count', 'max_distance', 'num_harvests'])
        
        # Convert types
        df['max_distance'] = pd.to_numeric(df['max_distance'], errors='coerce')
        df['ripe_count'] = pd.to_numeric(df['ripe_count'], errors='coerce')
        df['num_harvests'] = pd.to_numeric(df['num_harvests'], errors='coerce')
        
        # Calculate
        df['calculated_value'] = df['ripe_count'] / df['max_distance'] / df['num_harvests']
        
        print("\nSample Database Data (last 5 days):")
        print(df.to_string())
        print("\nFormula: ripe_count / max_distance / num_harvests")
        print(f"\nExample calculation for first row:")
        if len(df) > 0:
            row = df.iloc[0]
            print(f"  ripe_count: {row['ripe_count']}")
            print(f"  max_distance: {row['max_distance']}")
            print(f"  num_harvests: {row['num_harvests']}")
            print(f"  Result: {row['ripe_count']} / {row['max_distance']} / {row['num_harvests']} = {row['calculated_value']:.4f}")
    else:
        print("⚠️  No data returned from database")
        
except Exception as e:
    print(f"❌ Database error: {e}")

print("\n" + "="*80)
print("2. CH SHEET (Google Sheets)")
print("-" * 80)
print("\nCH Sheet loads 'Ripe Fruits per Meter' column directly from:")
print("  Google Sheet: Costa Continuous Harvesting")
print("  Column: 'Ripe Fruits per Meter'")
print("\nThis column is already pre-calculated in the Google Sheet.")
print("The dashboard reads it as-is and applies 7-day rolling average.")

print("\n" + "="*80)
print("3. BOTH ARE PLOTTED WITH 7-DAY ROLLING AVERAGE")
print("-" * 80)
print("\nBoth data sources get:")
print("  rolling_avg = data.rolling(window=7, min_periods=1).mean()")
print("\n" + "="*80)
