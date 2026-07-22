# Dashboard Deployment Troubleshooting

## Issue: Metrics Tab Not Loading on Render

If the Metrics Testing tab works locally but doesn't load on Render, here are the likely causes and solutions:

### Root Causes Fixed

1. **Missing Data from Sundrop/Westburg**
   - **Problem**: Sundrop and Westburg sheets had an extra "2025" row that caused data loading to fail
   - **Fix**: Added automatic detection to skip year-marker rows in both `load_data()` and `load_metrics_testing_data()`
   - **Result**: Now loads 276 rows for Sundrop and 287 for Westburg (previously only 1-2 rows)

2. **No Error Handling for Failed Data Loads**
   - **Problem**: If any metrics sheet failed to load on Render, the entire app would crash silently
   - **Fix**: Added comprehensive try/catch blocks around all metrics data loading
   - **Result**: Dashboard continues to work even if some data sources fail

3. **Missing Column Checks**
   - **Problem**: Charts would crash if required columns were missing from the data
   - **Fix**: Added validation for required columns in all chart creation functions
   - **Result**: Shows "Missing required data columns" message instead of crashing

4. **Database Timeout Issues**
   - **Problem**: Fruit Analytics database queries might timeout on Render's free tier
   - **Fix**: Reduced timeout from 240s to 30s and added better error handling
   - **Result**: App continues loading even if database is slow/unavailable

### How to Verify on Render

1. **Check Render logs** for data loading messages:
   ```
   ✅ Loaded 276 rows from Sundrop Metrics Testing
   ✅ Loaded 287 rows from Westburg Metrics Testing
   ✅ Combined metrics: XXX total rows
   ```

2. **Look for error messages**:
   - `⚠️  Error loading [Farm] Metrics Testing: [error]` - indicates a sheet failed to load
   - `⚠️  No metrics data loaded` - indicates all sheets failed

3. **Check the Metrics tab**:
   - Should show charts even if some farms have no data
   - If completely blank, check browser console for JavaScript errors

### Common Deployment Issues

#### Credentials Not Loaded
**Symptom**: All sheets fail to load
**Solution**: 
- Verify `credentials.json` is uploaded as a Secret File in Render
- OR verify `GOOGLE_CREDENTIALS_BASE64` environment variable is set

#### Memory Issues
**Symptom**: App crashes during startup
**Solution**: 
- Upgrade to a paid Render instance with more RAM
- Or reduce data loading (limit date ranges)

#### Database Connection Issues  
**Symptom**: Fruit Analytics data missing but app works
**Solution**:
- Add database connection credentials as environment variables
- Or accept that Fruit Analytics won't work on free tier

### Testing Locally

To test with similar constraints to production:

```bash
# Limit database timeout
export DB_TIMEOUT=30

# Run dashboard
python dashboard.py
```

### Emergency Fallback

If Metrics tab still won't load, you can disable it temporarily by commenting out the metrics data loading in dashboard.py:

```python
# Comment out lines 370-415 (metrics data loading)
# df_metrics = pd.DataFrame()  # Use empty dataframe
```

This will show "No metrics data available" messages but keep the app running.
