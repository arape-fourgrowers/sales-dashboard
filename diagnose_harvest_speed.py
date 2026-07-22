#!/usr/bin/env python3
"""Diagnose H&A Robot Harvest Speed data"""

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

def load_data(sheet_id, sheet_name):
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    
    data = worksheet.get_all_values()
    headers = data[1]
    
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    
    df = pd.DataFrame(data[2:], columns=unique_headers)
    
    datetime_col = None
    for col in df.columns:
        if 'datetime' in col.lower() and 'start' in col.lower():
            datetime_col = col
            break
    
    if datetime_col:
        df['Start Datetime'] = pd.to_datetime(df[datetime_col], errors='coerce')
    
    numeric_cols = ['Robot Harvest Speed', 'AMA Number', 'Ripe Fruits per Meter']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=['Start Datetime'])
    df = df.sort_values('Start Datetime')
    return df

# Load datasets
COSTA_SHEET_ID = "1pblkbokP6SP-YYeUIxvYZ9L0BJqcbFGjdY5DJRxbLb4"
COSTA_SHEET_NAME = "Costa Continuous Harvesting"
HA_SHEET_ID = '1DKtjOg62fYP2iHw-DpUDjsHWfmYaYcblBMKqxC0V9gc'
HA_SHEET_NAME = 'H&A Continuous Harvesting'

print("Loading Costa data...")
df_costa = load_data(COSTA_SHEET_ID, COSTA_SHEET_NAME)
df_costa['Farm'] = 'Costa'
print(f"✓ Loaded {len(df_costa)} rows")

print("\nLoading H&A data...")
df_ha = load_data(HA_SHEET_ID, HA_SHEET_NAME)
df_ha['Farm'] = 'H&A'
print(f"✓ Loaded {len(df_ha)} rows")

# Combine
df = pd.concat([df_costa, df_ha], ignore_index=True, sort=False)

# Calculate default date range (last 4 weeks)
max_date = df['Start Datetime'].max()
default_start = max_date - timedelta(weeks=4)

print("\n" + "="*80)
print("ROBOT HARVEST SPEED DATA SUMMARY")
print("="*80)

print(f"\nOverall date range: {df['Start Datetime'].min()} to {max_date}")
print(f"Default chart window: {default_start} to {max_date}")

# Analyze H&A specifically
print("\n" + "-"*80)
print("H&A DATA ANALYSIS:")
print("-"*80)

ha_speed = df_ha.dropna(subset=['Robot Harvest Speed'])
print(f"\nTotal H&A rows: {len(df_ha)}")
print(f"H&A rows with Robot Harvest Speed: {len(ha_speed)}")
print(f"Date range: {ha_speed['Start Datetime'].min()} to {ha_speed['Start Datetime'].max()}")
print(f"Value range: {ha_speed['Robot Harvest Speed'].min():.2f} to {ha_speed['Robot Harvest Speed'].max():.2f} sec/tomato")

# Check data in default window
ha_in_window = ha_speed[(ha_speed['Start Datetime'] >= default_start) & (ha_speed['Start Datetime'] <= max_date)]
print(f"\nH&A data points in default 4-week window: {len(ha_in_window)}")

if len(ha_in_window) > 0:
    print(f"Values in window: {ha_in_window['Robot Harvest Speed'].min():.2f} to {ha_in_window['Robot Harvest Speed'].max():.2f}")
    print("\nSample H&A data in window:")
    print(ha_in_window[['Start Datetime', 'Robot Harvest Speed']].head(10).to_string(index=False))
else:
    print("\n⚠️  NO H&A DATA IN DEFAULT WINDOW!")
    print(f"H&A data ends at: {ha_speed['Start Datetime'].max()}")
    print(f"Default window starts at: {default_start}")
    print(f"Gap: {(default_start - ha_speed['Start Datetime'].max()).days} days")

# Compare with Costa
print("\n" + "-"*80)
print("COSTA DATA ANALYSIS:")
print("-"*80)

costa_speed = df_costa.dropna(subset=['Robot Harvest Speed'])
print(f"\nTotal Costa rows: {len(df_costa)}")
print(f"Costa rows with Robot Harvest Speed: {len(costa_speed)}")
print(f"Date range: {costa_speed['Start Datetime'].min()} to {costa_speed['Start Datetime'].max()}")
print(f"Value range: {costa_speed['Robot Harvest Speed'].min():.2f} to {costa_speed['Robot Harvest Speed'].max():.2f} sec/tomato")

costa_in_window = costa_speed[(costa_speed['Start Datetime'] >= default_start) & (costa_speed['Start Datetime'] <= max_date)]
print(f"\nCosta data points in default 4-week window: {len(costa_in_window)}")

# Simulate what the chart function does
print("\n" + "="*80)
print("CHART SIMULATION (Both farms selected)")
print("="*80)

selected_farms = ['Costa', 'H&A']
chart_df = df[df['Farm'].isin(selected_farms)].copy()
chart_df = chart_df.dropna(subset=['Robot Harvest Speed']).copy()
chart_df = chart_df.sort_values('Start Datetime')

for farm in selected_farms:
    farm_df = chart_df[chart_df['Farm'] == farm].copy()
    farm_df['Rolling_Avg'] = farm_df['Robot Harvest Speed'].rolling(window=7, min_periods=1).mean()
    
    print(f"\n{farm}:")
    print(f"  Total points to plot: {len(farm_df)}")
    print(f"  Date range: {farm_df['Start Datetime'].min()} to {farm_df['Start Datetime'].max()}")
    print(f"  Rolling avg range: {farm_df['Rolling_Avg'].min():.2f} to {farm_df['Rolling_Avg'].max():.2f}")
    
    # Check in default window
    farm_in_window = farm_df[(farm_df['Start Datetime'] >= default_start) & (farm_df['Start Datetime'] <= max_date)]
    print(f"  Points in default window: {len(farm_in_window)}")
    
    if len(farm_in_window) > 0:
        print(f"  Last 5 points in window:")
        display_cols = ['Start Datetime', 'Robot Harvest Speed', 'Rolling_Avg']
        for _, row in farm_in_window.tail(5).iterrows():
            print(f"    {row['Start Datetime']}: {row['Robot Harvest Speed']:.2f} (rolling: {row['Rolling_Avg']:.2f})")

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80)
