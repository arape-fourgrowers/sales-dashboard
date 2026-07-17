import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Google Sheet ID from the URL
SHEET_ID = "1pblkbokP6SP-YYeUIxvYZ9L0BJqcbFGjdY5DJRxbLb4"
SHEET_NAME = "Costa Continuous Harvesting"

def import_specific_sheet(sheet_id, sheet_name, header_row=2, credentials_file='credentials.json'):
    """Import a specific sheet from a Google Spreadsheet
    
    Args:
        sheet_id: Google Sheet ID
        sheet_name: Name of the sheet to import
        header_row: Row number containing column headers (1-indexed)
        credentials_file: Path to service account credentials
    """
    
    # Define the scope
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    # Authenticate using service account
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Open the spreadsheet
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    
    # Get all values
    data = worksheet.get_all_values()
    
    if len(data) >= header_row:
        # Use specified row as headers (convert to 0-indexed)
        headers = data[header_row - 1]
        # Data starts after header row
        df = pd.DataFrame(data[header_row:], columns=headers)
        return df
    else:
        raise ValueError(f"Sheet has fewer than {header_row} rows")
    
    return None

# Main execution
if __name__ == "__main__":
    try:
        print(f"Importing sheet: '{SHEET_NAME}'")
        print(f"Sheet ID: {SHEET_ID}")
        print(f"Header row: 2\n")
        
        df = import_specific_sheet(SHEET_ID, SHEET_NAME, header_row=2)
        
        print(f"✓ Successfully loaded: {df.shape[0]} rows, {df.shape[1]} columns\n")
        
        print("="*60)
        print("COLUMN NAMES:")
        print("="*60)
        for i, col in enumerate(df.columns, 1):
            print(f"{i}. {col}")
        
        print("\n" + "="*60)
        print("FIRST ROW OF DATA:")
        print("="*60)
        print(df.iloc[0])
        
    except FileNotFoundError:
        print("\n❌ ERROR: credentials.json not found!")
        print("Please follow instructions in README_SHEETS.md to set up authentication.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nMake sure you've:")
        print("1. Created a service account and downloaded credentials.json")
        print("2. Shared the Google Sheet with the service account email")
        print("3. Installed required packages: pip install gspread google-auth")
