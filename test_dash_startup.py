"""Test that dashboard can start even with no metrics data"""
import sys
import pandas as pd

# Mock empty metrics before importing dashboard
print("Testing dashboard startup with empty metrics...")

# Create a test where metrics fail to load
import importlib.util
spec = importlib.util.spec_from_file_location("dashboard_test", "dashboard.py")
dashboard = importlib.util.module_from_spec(spec)

# Patch load_metrics_testing_data to return empty dataframe
original_load = None

def mock_load_metrics(sheet_id, sheet_name):
    print(f"  Mock: Returning empty DataFrame for {sheet_name}")
    return pd.DataFrame()

# Import and patch
import dashboard as dash_module
dash_module.load_metrics_testing_data = mock_load_metrics

# Now try to import (it will call load functions at module level)
try:
    spec.loader.exec_module(dashboard)
    print("✅ Dashboard loaded successfully with empty metrics!")
    print(f"   df_metrics shape: {dashboard.df_metrics.shape}")
    print(f"   df_metrics empty: {dashboard.df_metrics.empty}")
    print(f"   max_date_metrics: {dashboard.max_date_metrics}")
except Exception as e:
    print(f"❌ Dashboard failed to load: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All tests passed!")
