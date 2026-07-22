import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pg8000.native

# Database configuration
DB_HOST = 'fourgrowers-analytics-db.clswl6o06h7g.us-east-2.rds.amazonaws.com'
DB_NAME = 'postgres'
DB_PASS = 'FourGrowers2026!'
DB_USER = 'analyticsuser'

# Google Sheet configuration
COSTA_SHEET_ID = "1pblkbokP6SP-YYeUIxvYZ9L0BJqcbFGjdY5DJRxbLb4"
COSTA_SHEET_NAME = "Costa Continuous Harvesting"
COSTA_METRICS_SHEET = "Metrics Testing"

HA_SHEET_ID = "1DKtjOg62fYP2iHw-DpUDjsHWfmYaYcblBMKqxC0V9gc"
HA_SHEET_NAME = "H&A Continuous Harvesting"
HA_METRICS_SHEET = "Metrics Testing"

# Professional color scheme - FourGrowers branding
COLORS = {
    'background': '#ffffff',
    'surface': '#f8f9fa',
    'primary': '#2d6a4f',        # Forest green (main brand color)
    'primary_dark': '#1b4332',   # Darker green
    'secondary': '#40916c',      # Medium green
    'accent': '#52b788',         # Light green accent
    'text': '#1a1a1a',           # Near black for text
    'text_secondary': '#666666', # Gray for secondary text
    'grid': '#e8e8e8',           # Light gray grid
    'border': '#d4d4d4'          # Border color
}

# Plotly template
PLOTLY_TEMPLATE = {
    'layout': {
        'paper_bgcolor': COLORS['surface'],
        'plot_bgcolor': COLORS['surface'],
        'font': {'color': COLORS['text'], 'family': 'Segoe UI, sans-serif', 'size': 12},
        'title': {'font': {'size': 18, 'color': COLORS['text']}},
        'xaxis': {
            'gridcolor': COLORS['grid'],
            'linecolor': COLORS['grid'],
            'color': COLORS['text']
        },
        'yaxis': {
            'gridcolor': COLORS['grid'],
            'linecolor': COLORS['grid'],
            'color': COLORS['text']
        }
    }
}

def get_db_connection():
    """Connect to database"""
    try:
        conn = pg8000.native.Connection(
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            database=DB_NAME,
            timeout=120
        )
        return conn
    except Exception as e:
        print(f"⚠️  DB Connection Error: {e}")
        return None

def load_fruit_analytics_data(farm_id='costa'):
    """Load Ripe Fruits per Meter from database using harvest events"""
    print(f"Loading Fruit Analytics data for {farm_id}...")
    
    try:
        conn = get_db_connection()
        if not conn:
            print(f"⚠️  Skipping Fruit Analytics - database connection failed")
            return pd.DataFrame()
        
        # Query per day: ripe_count / max_distance / num_harvests
        query = """
        SELECT
            DATE("timestamp") AS harvest_date,
            COUNT(*) FILTER (WHERE ("data"->>'Ripeness')::float >= 4) AS ripe_count,
            MAX(("data"->>'x (m)')::float) AS max_distance,
            COUNT(DISTINCT "timestamp") AS num_harvests
        FROM farm_events
        WHERE farm_id = :farm_id
            AND event_type = 'harvest'
            AND "timestamp" >= CURRENT_DATE - INTERVAL '120 days'
            AND ("data"->>'Ripeness') IS NOT NULL
            AND ("data"->>'x (m)') IS NOT NULL
        GROUP BY DATE("timestamp")
        HAVING MAX(("data"->>'x (m)')::float) > 0
        ORDER BY harvest_date DESC
        LIMIT 60
        """
        
        # Set a statement timeout
        conn.run("SET statement_timeout = 240000")  # 240 seconds
        result = conn.run(query, farm_id=farm_id)
        conn.close()
        
        if not result:
            print(f"⚠️  No Fruit Analytics data found for {farm_id}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(result, columns=['harvest_date', 'ripe_count', 'max_distance', 'num_harvests'])
        
        # Convert to numeric types (handle Decimal objects from database)
        df['max_distance'] = pd.to_numeric(df['max_distance'], errors='coerce')
        df['ripe_count'] = pd.to_numeric(df['ripe_count'], errors='coerce')
        df['num_harvests'] = pd.to_numeric(df['num_harvests'], errors='coerce')
        
        # Remove rows with zero or null distance or harvests
        df = df[(df['max_distance'] > 0) & (df['num_harvests'] > 0)].copy()
        
        # Calculate ripe fruits per meter per harvest
        df['ripe_fruits_per_meter'] = df['ripe_count'] / df['max_distance'] / df['num_harvests']
        
        # Convert date to datetime
        df['harvest_date'] = pd.to_datetime(df['harvest_date'])
        
        # Sort by date ascending for proper time series
        df = df.sort_values('harvest_date')
        
        print(f"✅ Loaded {len(df)} days of Fruit Analytics data for {farm_id}")
        return df
        
    except Exception as e:
        print(f"⚠️  Error loading Fruit Analytics data for {farm_id}: {str(e)[:200]}")
        return pd.DataFrame()

def load_data(sheet_id, sheet_name):
    """Load data from Google Sheets"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    
    data = worksheet.get_all_values()
    headers = data[1]  # Row 2 has headers
    
    # Handle duplicate column names by making them unique
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    
    df = pd.DataFrame(data[2:], columns=unique_headers)  # Data starts at row 3
    
    # Standardize datetime column name
    datetime_col = None
    for col in df.columns:
        if 'datetime' in col.lower() and 'start' in col.lower():
            datetime_col = col
            break
    
    if datetime_col:
        df['Start Datetime'] = pd.to_datetime(df[datetime_col], errors='coerce')
    else:
        raise ValueError(f"Could not find datetime column in {sheet_name}")
    
    # Convert numeric columns
    numeric_cols = [
        'Ripe Fruits per Meter',
        'Robot Harvest Speed',
        'AMA Number',
        'Harvest \nWeight (kg)\nRobot Scale',
        'Average Fruit Weight (g)',
    ]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Remove rows with invalid dates
    df = df.dropna(subset=['Start Datetime'])
    
    # Sort by date
    df = df.sort_values('Start Datetime')
    
    return df

def load_metrics_testing_data(sheet_id, sheet_name):
    """Load Metrics Testing data from Google Sheets"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    
    data = worksheet.get_all_values()
    headers = data[1]  # Row 2 has headers
    
    # Handle duplicate column names by making them unique
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    
    df = pd.DataFrame(data[2:], columns=unique_headers)  # Data starts at row 3
    
    # Standardize datetime column name
    datetime_col = None
    for col in df.columns:
        if 'datetime' in col.lower() and 'start' in col.lower():
            datetime_col = col
            break
    
    if datetime_col:
        df['Start Datetime'] = pd.to_datetime(df[datetime_col], errors='coerce')
    else:
        raise ValueError(f"Could not find datetime column in {sheet_name}")
    
    # Define percentage columns (need special handling to remove % sign)
    percentage_cols = [
        'Recall w/ Questionable',
        'Precision w/ Questionable',
        'Drop Rate',
    ]
    
    # Convert percentage columns (remove % and divide by 100)
    for col in percentage_cols:
        if col in df.columns:
            # Replace error values and empty strings with NaN, then convert
            df[col] = df[col].replace(['#DIV/0!', '#VALUE!', '#N/A', '', ' '], '0')
            df[col] = df[col].str.replace('%', '')
            df[col] = pd.to_numeric(df[col], errors='coerce') / 100
    
    # Convert other numeric columns
    numeric_cols = [
        'Ripe Fruits per meter',
        'Real Harvest Speed',
    ]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Remove rows with invalid dates
    df = df.dropna(subset=['Start Datetime'])
    
    # Sort by date
    df = df.sort_values('Start Datetime')
    
    return df

# Load the data
print("Loading data from Google Sheets...")
df_costa = load_data(COSTA_SHEET_ID, COSTA_SHEET_NAME)
print(f"Loaded {len(df_costa)} rows from Costa")
df_costa['Farm'] = 'Costa'

df_ha = load_data(HA_SHEET_ID, HA_SHEET_NAME)
print(f"Loaded {len(df_ha)} rows from H&A")
df_ha['Farm'] = 'H&A'

# Combine both farms
df = pd.concat([df_costa, df_ha], ignore_index=True, sort=False)

# Load Fruit Analytics data from database
print("Loading Fruit Analytics data from database...")
df_fruit_analytics_costa = load_fruit_analytics_data('costa')
df_fruit_analytics_ha = load_fruit_analytics_data('h&a')

print("Loading Metrics Testing data...")
df_metrics_costa = load_metrics_testing_data(COSTA_SHEET_ID, COSTA_METRICS_SHEET)
print(f"Loaded {len(df_metrics_costa)} rows from Costa Metrics Testing")
df_metrics_costa['Farm'] = 'Costa'

df_metrics_ha = load_metrics_testing_data(HA_SHEET_ID, HA_METRICS_SHEET)
print(f"Loaded {len(df_metrics_ha)} rows from H&A Metrics Testing")
df_metrics_ha['Farm'] = 'H&A'

# Combine both farms
df_metrics = pd.concat([df_metrics_costa, df_metrics_ha], ignore_index=True, sort=False)

# Calculate default date range (last 4 weeks)
max_date = df['Start Datetime'].max()
default_start = max_date - timedelta(weeks=4)

# Calculate default date range for metrics testing (last 4 weeks)
max_date_metrics = df_metrics['Start Datetime'].max()
default_start_metrics = max_date_metrics - timedelta(weeks=4)

# Initialize the Dash app
app = Dash(__name__)

# Define the layout
app.layout = html.Div([
    # Header section
    html.Div([
        html.Div([
            html.H1("Harvest Analytics Dashboard", style={
                'margin': '0',
                'fontSize': '28px',
                'fontWeight': '600',
                'color': COLORS['primary'],
                'fontFamily': 'system-ui, -apple-system, sans-serif'
            }),
            html.P("Real-time performance metrics for continuous harvesting operations", style={
                'margin': '8px 0 0 0',
                'fontSize': '14px',
                'color': COLORS['text_secondary'],
            })
        ], style={'flex': '1'}),
        
        html.Div([
            html.Div([
                html.Span("●", style={'color': COLORS['accent'], 'fontSize': '16px', 'marginRight': '8px'}),
                html.Span("Live Data", style={
                    'fontSize': '13px',
                    'fontWeight': '500',
                    'color': COLORS['text']
                })
            ], style={'display': 'flex', 'alignItems': 'center'})
        ])
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '24px 40px',
        'background': COLORS['background'],
        'borderBottom': f'3px solid {COLORS["primary"]}',
        'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.08)'
    }),
    
    # Farm selector
    html.Div([
        html.Label("Select Farms:", style={
            'fontWeight': '600',
            'fontSize': '14px',
            'marginRight': '16px',
            'color': COLORS['text']
        }),
        dcc.Checklist(
            id='farm-selector',
            options=[
                {'label': ' Costa', 'value': 'Costa'},
                {'label': ' H&A', 'value': 'H&A'}
            ],
            value=['Costa', 'H&A'],
            inline=True,
            style={'display': 'inline-block'},
            labelStyle={
                'marginRight': '20px',
                'fontSize': '14px',
                'fontWeight': '500'
            }
        )
    ], style={
        'padding': '16px 40px',
        'background': COLORS['background'],
        'borderBottom': f'1px solid {COLORS["border"]}',
        'display': 'flex',
        'alignItems': 'center'
    }),
    
    # Tabs
    html.Div([
        dcc.Tabs(id='tabs', value='tab-1', children=[
            dcc.Tab(label='Performance Dashboard', value='tab-1', style={
                'padding': '12px 24px',
                'fontWeight': '500',
                'borderBottom': f'3px solid transparent'
            }, selected_style={
                'padding': '12px 24px',
                'fontWeight': '600',
                'borderBottom': f'3px solid {COLORS["primary"]}',
                'color': COLORS['primary']
            }),
            dcc.Tab(label='Metrics Testing', value='tab-2', style={
                'padding': '12px 24px',
                'fontWeight': '500',
                'borderBottom': f'3px solid transparent'
            }, selected_style={
                'padding': '12px 24px',
                'fontWeight': '600',
                'borderBottom': f'3px solid {COLORS["primary"]}',
                'color': COLORS['primary']
            }),
            dcc.Tab(label='Client Scorecard', value='tab-3', style={
                'padding': '12px 24px',
                'fontWeight': '500',
                'borderBottom': f'3px solid transparent'
            }, selected_style={
                'padding': '12px 24px',
                'fontWeight': '600',
                'borderBottom': f'3px solid {COLORS["primary"]}',
                'color': COLORS['primary']
            }),
            dcc.Tab(label='Business Case Calculator', value='tab-4', style={
                'padding': '12px 24px',
                'fontWeight': '500',
                'borderBottom': f'3px solid transparent'
            }, selected_style={
                'padding': '12px 24px',
                'fontWeight': '600',
                'borderBottom': f'3px solid {COLORS["primary"]}',
                'color': COLORS['primary']
            }),
        ], style={
            'borderBottom': f'1px solid {COLORS["border"]}'
        })
    ], style={'background': COLORS['background'], 'padding': '0 40px'}),
    
    # Tab content with loading overlay
    dcc.Loading(
        id="loading",
        type="circle",
        fullscreen=False,
        color=COLORS['primary'],
        style={
            'position': 'absolute',
            'top': '50%',
            'left': '50%',
            'transform': 'translate(-50%, -50%)',
            'zIndex': 9999
        },
        children=html.Div(id='tabs-content', style={
            'minHeight': '600px',
            'position': 'relative'
        })
    ),
    
    # Footer
    html.Div([
        html.P(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data Source: Google Sheets", style={
            'margin': '0',
            'fontSize': '12px',
            'color': COLORS['text_secondary'],
            'textAlign': 'center'
        })
    ], style={
        'padding': '16px',
        'background': COLORS['background'],
        'borderTop': f'1px solid {COLORS["border"]}'
    })
], style={
    'backgroundColor': COLORS['surface'],
    'minHeight': '100vh',
    'fontFamily': 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    'color': COLORS['text']
})

# Callback to render tab content
@callback(
    Output('tabs-content', 'children'),
    Input('tabs', 'value'),
    Input('farm-selector', 'value')
)
def render_content(tab, selected_farms):
    if not selected_farms:
        selected_farms = []
    
    if tab == 'tab-1':
        return html.Div([
            # Chart 1: Ripe Fruits per Meter
            html.Div([
                dcc.Graph(id='ripe-fruits-per-meter', figure=create_ripe_fruits_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            # Chart 2: Robot Harvest Speed
            html.Div([
                dcc.Graph(id='robot-harvest-speed', figure=create_harvest_speed_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            # Chart 3: Harvest Weight
            html.Div([
                dcc.Graph(id='harvest-weight', figure=create_harvest_weight_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            # Chart 4: Average Fruit Weight
            html.Div([
                dcc.Graph(id='average-fruit-weight', figure=create_fruit_weight_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
        ], style={'padding': '32px 40px', 'maxWidth': '1400px', 'margin': '0 auto', 'background': COLORS['surface']})
    
    elif tab == 'tab-2':
        return html.Div([
            # Metrics Testing Charts
            html.Div([
                dcc.Graph(id='metrics-ripe-fruits', figure=create_metrics_ripe_fruits_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            html.Div([
                dcc.Graph(id='metrics-recall', figure=create_metrics_recall_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            html.Div([
                dcc.Graph(id='metrics-precision', figure=create_metrics_precision_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            html.Div([
                dcc.Graph(id='metrics-harvest-speed', figure=create_metrics_harvest_speed_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            html.Div([
                dcc.Graph(id='metrics-drop-rate', figure=create_metrics_drop_rate_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
            
            html.Div([
                dcc.Graph(id='metrics-savings', figure=create_metrics_savings_figure(selected_farms), config={'displayModeBar': True, 'displaylogo': False})
            ], style={
                'background': COLORS['background'],
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '20px',
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                'border': f'1px solid {COLORS["border"]}'
            }),
        ], style={'padding': '32px 40px', 'maxWidth': '1400px', 'margin': '0 auto', 'background': COLORS['surface']})
    
    elif tab == 'tab-3':
        return create_client_scorecard_tab(selected_farms)
    
    elif tab == 'tab-4':
        return create_business_case_calculator_tab()

def calculate_client_metrics(farm_name):
    """Calculate current metrics for a farm from the last 6 weeks of data"""
    from datetime import datetime, timedelta
    
    cutoff = datetime.now() - timedelta(weeks=6)
    
    # Get Metrics Testing data for this farm
    if farm_name == 'Costa':
        farm_metrics = df_metrics_costa[df_metrics_costa['Start Datetime'] >= cutoff].copy()
    else:  # H&A
        farm_metrics = df_metrics_ha[df_metrics_ha['Start Datetime'] >= cutoff].copy()
    
    # Get Continuous Harvesting data for full row metrics
    if farm_name == 'Costa':
        farm_ch = df_costa[df_costa['Start Datetime'] >= cutoff].copy()
    else:
        farm_ch = df_ha[df_ha['Start Datetime'] >= cutoff].copy()
    
    metrics = {}
    
    # Speed (Metrics Test) - Real Harvest Speed converted to kg/hr
    # Formula: (fruit_weight_g / speed_sec_per_tomato * 3600) / 1000
    if 'Real Harvest Speed' in farm_metrics.columns and len(farm_metrics) > 0:
        valid_speeds = farm_metrics[farm_metrics['Real Harvest Speed'].notna() & (farm_metrics['Real Harvest Speed'] > 0)]
        if len(valid_speeds) > 0:
            avg_speed_sec = valid_speeds['Real Harvest Speed'].mean()
            # Assume average fruit weight of 11g
            metrics['speed_metrics'] = (11.0 / avg_speed_sec * 3600) / 1000
            metrics['speed_metrics_trend'] = valid_speeds['Real Harvest Speed'].values
        else:
            metrics['speed_metrics'] = None
            metrics['speed_metrics_trend'] = []
    
    # Speed (Full Row) - from Robot Harvest Speed in CH sheet, also convert to kg/hr
    if 'Robot Harvest Speed' in farm_ch.columns and len(farm_ch) > 0:
        valid_speeds = farm_ch[farm_ch['Robot Harvest Speed'].notna() & (farm_ch['Robot Harvest Speed'] > 0)]
        if len(valid_speeds) > 0:
            avg_speed_sec = valid_speeds['Robot Harvest Speed'].mean()
            metrics['speed_full_row'] = (11.0 / avg_speed_sec * 3600) / 1000
            metrics['speed_full_row_trend'] = valid_speeds['Robot Harvest Speed'].values
        else:
            metrics['speed_full_row'] = None
            metrics['speed_full_row_trend'] = []
    
    # Recall (Metrics Test)
    if 'Recall w/ Questionable' in farm_metrics.columns and len(farm_metrics) > 0:
        valid_recall = farm_metrics[farm_metrics['Recall w/ Questionable'].notna()]
        if len(valid_recall) > 0:
            metrics['recall_metrics'] = valid_recall['Recall w/ Questionable'].mean()
            metrics['recall_metrics_trend'] = valid_recall['Recall w/ Questionable'].values
        else:
            metrics['recall_metrics'] = None
            metrics['recall_metrics_trend'] = []
    
    # Precision (Metrics Test)
    if 'Precision w/ Questionable' in farm_metrics.columns and len(farm_metrics) > 0:
        valid_precision = farm_metrics[farm_metrics['Precision w/ Questionable'].notna()]
        if len(valid_precision) > 0:
            metrics['precision_metrics'] = valid_precision['Precision w/ Questionable'].mean()
            metrics['precision_metrics_trend'] = valid_precision['Precision w/ Questionable'].values
        else:
            metrics['precision_metrics'] = None
            metrics['precision_metrics_trend'] = []
    
    # Reliability - calculated as (1 - Drop Rate)
    if 'Drop Rate' in farm_metrics.columns and len(farm_metrics) > 0:
        valid_drop = farm_metrics[farm_metrics['Drop Rate'].notna()]
        if len(valid_drop) > 0:
            avg_drop = valid_drop['Drop Rate'].mean()
            metrics['reliability'] = 1 - avg_drop
            metrics['reliability_trend'] = (1 - valid_drop['Drop Rate']).values
        else:
            metrics['reliability'] = None
            metrics['reliability_trend'] = []
    
    return metrics

def get_stoplight_color(value, goal, reverse=False):
    """Determine stoplight color based on value vs goal
    reverse=True means lower is better (like for drop rate)
    """
    if value is None or goal is None:
        return '#cccccc'  # Gray for no data
    
    ratio = value / goal if not reverse else goal / value
    
    if ratio >= 1.0:
        return '#4caf50'  # Green
    elif ratio >= 0.85:
        return '#ffeb3b'  # Yellow
    else:
        return '#f44336'  # Red

def create_client_scorecard_tab(selected_farms):
    """Create the Client Scorecard tab showing current performance vs goals"""
    
    # Only show Costa and H&A
    farms_to_show = [f for f in ['Costa', 'H&A'] if f in selected_farms]
    
    if not farms_to_show:
        return html.Div([
            html.H2("Please select Costa and/or H&A to view scorecard", 
                   style={'textAlign': 'center', 'padding': '40px', 'color': COLORS['text_secondary']})
        ])
    
    # Goals (hardcoded as requested)
    goals = {
        'Costa': {
            'speed_metrics': 21,  # kg/hr (20 RFPM)
            'speed_full_row': 21,
            'recall_metrics': None,  # No specific goal shown
            'recall_full_row': 0.60,
            'precision_metrics': 0.98,
            'precision_full_row_min': 0.70,
            'precision_full_row_max': 0.95,
            'reliability': 0.95,
        },
        'H&A': {
            'speed_metrics': 40,  # kg/hr
            'speed_full_row': 40,
            'recall_metrics': None,
            'recall_full_row_min': 0.40,
            'recall_full_row_max': 0.50,
            'precision_metrics': 0.98,
            'precision_full_row_min': 0.85,
            'precision_full_row_max': 0.90,
            'reliability': 0.95,
        }
    }
    
    # Calculate current metrics for each farm
    farm_data = {}
    for farm in farms_to_show:
        farm_data[farm] = calculate_client_metrics(farm)
    
    # Create table rows
    table_rows = []
    
    # Header row
    header_cells = [html.Th('Client', style={'padding': '16px', 'textAlign': 'left', 'borderBottom': f'2px solid {COLORS["border"]}'})]
    columns = [
        'Speed (Metrics Test)',
        'Speed (Full Row)',
        'Recall',
        'Recall (full row)',
        'Precision',
        'Precision (full row)',
        'Reliability',
        'Quality',
        'Commitment'
    ]
    for col in columns:
        header_cells.append(html.Th(col, style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'2px solid {COLORS["border"]}', 'minWidth': '120px'}))
    
    table_rows.append(html.Tr(header_cells))
    
    # Data rows for each farm
    for farm in farms_to_show:
        metrics = farm_data[farm]
        goal_set = goals[farm]
        cells = []
        
        # Farm name
        cells.append(html.Td(farm, style={'padding': '16px', 'fontWeight': '600', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Speed (Metrics Test)
        speed_m = metrics.get('speed_metrics')
        goal_speed_m = goal_set['speed_metrics']
        if speed_m:
            color = get_stoplight_color(speed_m, goal_speed_m)
            trend_text = f"Last 6 weeks: {', '.join([f'{(11.0/v*3600/1000):.1f}' for v in metrics.get('speed_metrics_trend', [])[-5:]])}"
            cells.append(html.Td(
                html.Div([
                    html.Span('● ', style={'color': color, 'fontSize': '24px', 'marginRight': '8px'}),
                    html.Span(f'{speed_m:.1f} / {goal_speed_m} kg/hr', style={'fontWeight': '500'})
                ], title=trend_text),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Speed (Full Row)
        speed_f = metrics.get('speed_full_row')
        goal_speed_f = goal_set['speed_full_row']
        if speed_f:
            color = get_stoplight_color(speed_f, goal_speed_f)
            trend_text = f"Last 6 weeks: {', '.join([f'{(11.0/v*3600/1000):.1f}' for v in metrics.get('speed_full_row_trend', [])[-5:]])}"
            cells.append(html.Td(
                html.Div([
                    html.Span('● ', style={'color': color, 'fontSize': '24px', 'marginRight': '8px'}),
                    html.Span(f'{speed_f:.1f} / {goal_speed_f} kg/hr', style={'fontWeight': '500'})
                ], title=trend_text),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Recall (Metrics Test)
        recall_m = metrics.get('recall_metrics')
        if recall_m:
            # Use green if > 70%
            color = '#4caf50' if recall_m >= 0.70 else ('#ffeb3b' if recall_m >= 0.60 else '#f44336')
            trend_text = f"Last 6 weeks: {', '.join([f'{v:.1%}' for v in metrics.get('recall_metrics_trend', [])[-5:]])}"
            cells.append(html.Td(
                html.Div([
                    html.Span('● ', style={'color': color, 'fontSize': '24px', 'marginRight': '8px'}),
                    html.Span(f'{recall_m:.0%}', style={'fontWeight': '500'})
                ], title=trend_text),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Recall (Full Row) - show as range with goal, using red/yellow coloring
        recall_full_goal = goal_set.get('recall_full_row')
        if recall_full_goal:
            # For display, just show the goal since we don't have full row recall in data
            cells.append(html.Td(
                html.Div([
                    html.Span('🔴 ', style={'fontSize': '16px', 'marginRight': '8px'}),
                    html.Span(f'{recall_full_goal:.0%}', style={'fontWeight': '500'})
                ]),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Precision (Metrics Test)
        precision_m = metrics.get('precision_metrics')
        goal_precision = goal_set['precision_metrics']
        if precision_m:
            color = get_stoplight_color(precision_m, goal_precision)
            trend_text = f"Last 6 weeks: {', '.join([f'{v:.1%}' for v in metrics.get('precision_metrics_trend', [])[-5:]])}"
            cells.append(html.Td(
                html.Div([
                    html.Span('● ', style={'color': color, 'fontSize': '24px', 'marginRight': '8px'}),
                    html.Span(f'{precision_m:.0%} / {goal_precision:.0%}', style={'fontWeight': '500'})
                ], title=trend_text),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Precision (Full Row) - show as range
        precision_full_min = goal_set.get('precision_full_row_min')
        precision_full_max = goal_set.get('precision_full_row_max')
        if precision_full_min and precision_full_max:
            cells.append(html.Td(
                html.Div([
                    html.Span('🔴 ', style={'fontSize': '16px', 'marginRight': '8px'}),
                    html.Span(f'{precision_full_min:.0%}–{precision_full_max:.0%}', style={'fontWeight': '500'})
                ]),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Reliability
        reliability = metrics.get('reliability')
        goal_reliability = goal_set['reliability']
        if reliability:
            color = get_stoplight_color(reliability, goal_reliability)
            trend_text = f"Last 6 weeks: {', '.join([f'{v:.1%}' for v in metrics.get('reliability_trend', [])[-5:]])}"
            cells.append(html.Td(
                html.Div([
                    html.Span('● ', style={'color': color, 'fontSize': '24px', 'marginRight': '8px'}),
                    html.Span(f'{reliability:.0%} / {goal_reliability:.0%}', style={'fontWeight': '500'})
                ], title=trend_text),
                style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
            ))
        else:
            cells.append(html.Td('⚪ TBD', style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        # Quality - hardcoded as "Same as manual" with green
        cells.append(html.Td(
            html.Div([
                html.Span('🟢 ', style={'fontSize': '16px', 'marginRight': '8px'}),
                html.Span('Same as manual', style={'fontWeight': '500'})
            ]),
            style={'padding': '16px', 'textAlign': 'center', 'borderBottom': f'1px solid {COLORS["border"]}'}
        ))
        
        # Commitment
        cells.append(html.Td('✅', style={'padding': '16px', 'textAlign': 'center', 'fontSize': '20px', 'borderBottom': f'1px solid {COLORS["border"]}'}))
        
        table_rows.append(html.Tr(cells))
    
    return html.Div([
        html.H2("Client Performance Scorecard", style={
            'fontSize': '24px',
            'fontWeight': '600',
            'color': COLORS['primary'],
            'marginBottom': '8px'
        }),
        html.P("Current performance vs goals (based on last 6 weeks of data). Hover over stoplight indicators for trend data.", style={
            'fontSize': '14px',
            'color': COLORS['text_secondary'],
            'marginBottom': '30px'
        }),
        
        html.Div([
            html.Table(table_rows, style={
                'width': '100%',
                'borderCollapse': 'collapse',
                'background': COLORS['background'],
                'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)'
            })
        ], style={
            'overflowX': 'auto',
            'background': COLORS['background'],
            'borderRadius': '8px',
            'padding': '0',
            'border': f'1px solid {COLORS["border"]}'
        })
    ], style={'padding': '32px 40px', 'maxWidth': '1600px', 'margin': '0 auto', 'background': COLORS['surface']})

def create_business_case_calculator_tab():
    """Create the Business Case Calculator tab (moved from original location)"""
    return html.Div([
        html.H2("Business Case Calculator", style={
            'fontSize': '24px',
            'fontWeight': '600',
            'color': COLORS['primary'],
            'marginBottom': '20px'
        }),
        
        html.P("Adjust the parameters below to calculate savings relative to status quo:", style={
            'fontSize': '14px',
            'color': COLORS['text_secondary'],
            'marginBottom': '30px'
        }),
        
        # Input grid
        html.Div([
            # Column 1
            html.Div([
                html.Div([
                    html.Label("Fruit Weight (g)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-fruit-weight', type='number', value=11.0, step=0.1, 
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Harvesting Time (hrs)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-harvest-time', type='number', value=22.0, step=0.5,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Annual Production (kg/yr)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-annual-production', type='number', value=1386000.0, step=1000,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Base Harvesting Cost (CAD/kg)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-base-cost', type='number', value=0.44, step=0.01,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
            ], style={'flex': '1', 'marginRight': '20px'}),
            
            # Column 2
            html.Div([
                html.Div([
                    html.Label("Robot Speed (sec/tomato)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-robot-speed', type='number', value=1.0, step=0.1,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Recall (0-1)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-recall', type='number', value=0.9, min=0, max=1, step=0.01,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Precision (0-1)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-precision', type='number', value=0.10, min=0, max=1, step=0.01,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
            ], style={'flex': '1', 'marginRight': '20px'}),
            
            # Column 3
            html.Div([
                html.Div([
                    html.Label("Fruitdrop Human (%)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-fruitdrop-human', type='number', value=3.5, step=0.1,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("Fruitdrop Robot (%)", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-fruitdrop-robot', type='number', value=0.5, step=0.1,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("B80 Multiplier", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-b80', type='number', value=0.01, step=0.001,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
                
                html.Div([
                    html.Label("B81 Multiplier", style={'fontWeight': '600', 'marginBottom': '8px', 'display': 'block'}),
                    dcc.Input(id='input-b81', type='number', value=1.0, step=0.1,
                             style={'width': '100%', 'padding': '8px', 'borderRadius': '4px', 'border': f'1px solid {COLORS["border"]}'})
                ], style={'marginBottom': '20px'}),
            ], style={'flex': '1'}),
        ], style={'display': 'flex', 'marginBottom': '40px'}),
        
        # Result display
        html.Div([
            html.H3("Savings Relative to Status Quo", style={
                'fontSize': '20px',
                'fontWeight': '600',
                'marginBottom': '20px',
                'textAlign': 'center'
            }),
            html.Div(id='calculator-result', style={
                'fontSize': '64px',
                'fontWeight': '700',
                'textAlign': 'center',
                'padding': '40px',
                'borderRadius': '12px',
                'boxShadow': '0 4px 12px rgba(0, 0, 0, 0.1)'
            })
        ], style={
            'background': COLORS['background'],
            'borderRadius': '8px',
            'padding': '40px',
            'border': f'1px solid {COLORS["border"]}'
        })
    ], style={'padding': '32px 40px', 'maxWidth': '1200px', 'margin': '0 auto', 'background': COLORS['surface']})

# Create static figures with default 4-week view
def create_ripe_fruits_figure(selected_farms):
    """Chart 1: Ripe Fruits per Meter over time (all robots grouped) - 7 day rolling average"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values
    chart_df = chart_df.dropna(subset=['Ripe Fruits per Meter']).copy()
    chart_df = chart_df.sort_values('Start Datetime')
    
    fig = go.Figure()
    
    # Add CH Sheet data (original Google Sheets data)
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = chart_df[chart_df['Farm'] == farm].copy()
            # Calculate 7-day rolling average per farm
            farm_df['Rolling_Avg'] = farm_df['Ripe Fruits per Meter'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=farm_df['Start Datetime'],
                y=farm_df['Rolling_Avg'],
                mode='lines',
                name=f'{farm} - CH Sheet',
                line=dict(color=farm_colors.get(farm, COLORS['primary']), width=3)
            ))
    else:
        # Single farm or aggregated view
        chart_df['Rolling_Avg'] = chart_df['Ripe Fruits per Meter'].rolling(window=7, min_periods=1).mean()
        
        fig.add_trace(go.Scatter(
            x=chart_df['Start Datetime'],
            y=chart_df['Rolling_Avg'],
            mode='lines',
            name='CH Sheet',
            line=dict(color=COLORS['primary'], width=3),
            fill='tozeroy',
            fillcolor='rgba(45, 106, 79, 0.1)'
        ))
    
    # Add Fruit Analytics data (from database)
    if len(selected_farms) > 1:
        # Show both farms' Fruit Analytics with distinct colors
        fruit_analytics_colors = {
            'Costa': '#e76f51',  # Coral/orange
            'H&A': '#f4a261'     # Sandy orange
        }
        
        for farm in selected_farms:
            if farm == 'Costa' and not df_fruit_analytics_costa.empty:
                fa_df = df_fruit_analytics_costa.copy()
                fa_df['Rolling_Avg'] = fa_df['ripe_fruits_per_meter'].rolling(window=7, min_periods=1).mean()
                
                fig.add_trace(go.Scatter(
                    x=fa_df['harvest_date'],
                    y=fa_df['Rolling_Avg'],
                    mode='lines',
                    name='Costa - Fruit Analytics',
                    line=dict(color=fruit_analytics_colors['Costa'], width=3, dash='dash')
                ))
            elif farm == 'H&A' and not df_fruit_analytics_ha.empty:
                fa_df = df_fruit_analytics_ha.copy()
                fa_df['Rolling_Avg'] = fa_df['ripe_fruits_per_meter'].rolling(window=7, min_periods=1).mean()
                
                fig.add_trace(go.Scatter(
                    x=fa_df['harvest_date'],
                    y=fa_df['Rolling_Avg'],
                    mode='lines',
                    name='H&A - Fruit Analytics',
                    line=dict(color=fruit_analytics_colors['H&A'], width=3, dash='dash')
                ))
    else:
        # Single farm view
        if 'Costa' in selected_farms and not df_fruit_analytics_costa.empty:
            fa_df = df_fruit_analytics_costa.copy()
            fa_df['Rolling_Avg'] = fa_df['ripe_fruits_per_meter'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=fa_df['harvest_date'],
                y=fa_df['Rolling_Avg'],
                mode='lines',
                name='Fruit Analytics',
                line=dict(color='#e76f51', width=3, dash='dash')
            ))
        elif 'H&A' in selected_farms and not df_fruit_analytics_ha.empty:
            fa_df = df_fruit_analytics_ha.copy()
            fa_df['Rolling_Avg'] = fa_df['ripe_fruits_per_meter'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=fa_df['harvest_date'],
                y=fa_df['Rolling_Avg'],
                mode='lines',
                name='Fruit Analytics',
                line=dict(color='#e76f51', width=3, dash='dash')
            ))
    
    # Set default x-axis range to last 4 weeks
    fig.update_xaxes(range=[default_start, max_date])
    
    fig.update_layout(
        title={
            'text': 'Ripe Fruits per Meter',
            'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}
        },
        xaxis_title='',
        yaxis_title='Fruits per Meter',
        height=400,
        hovermode='x unified',
        xaxis=dict(
            rangeslider=dict(visible=True, bgcolor=COLORS['surface']),
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True
        ),
        yaxis=dict(
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True,
            zeroline=False
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_harvest_speed_figure(selected_farms):
    """Chart 2: Robot Harvest Speed over time - aggregated by farm when both selected"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values
    chart_df = chart_df.dropna(subset=['Robot Harvest Speed']).copy()
    chart_df = chart_df.sort_values('Start Datetime')
    
    fig = go.Figure()
    
    # If both farms are selected, show separate lines per farm
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = chart_df[chart_df['Farm'] == farm].copy()
            # Calculate 7-day rolling average per farm
            farm_df['Rolling_Avg'] = farm_df['Robot Harvest Speed'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=farm_df['Start Datetime'],
                y=farm_df['Rolling_Avg'],
                mode='lines',
                name=farm,
                line=dict(width=3, color=farm_colors.get(farm, COLORS['primary']))
            ))
    else:
        # Single farm - show by robot
        chart_df = chart_df[chart_df['AMA Number'] > 0]
        chart_df['Robot'] = 'Robot ' + chart_df['AMA Number'].astype(int).astype(str)
        
        robot_colors = [
            COLORS['primary'],
            COLORS['secondary'],
            COLORS['accent'],
            '#74c69d',
            '#95d5b2',
            '#b7e4c7',
            '#d8f3dc'
        ]
        
        for idx, robot in enumerate(sorted(chart_df['Robot'].unique())):
            robot_df = chart_df[chart_df['Robot'] == robot].copy()
            robot_df['Rolling_Avg'] = robot_df['Robot Harvest Speed'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=robot_df['Start Datetime'],
                y=robot_df['Rolling_Avg'],
                mode='lines',
                name=robot,
                line=dict(width=2.5, color=robot_colors[idx % len(robot_colors)])
            ))
    
    # Set default x-axis range to last 4 weeks
    fig.update_xaxes(range=[default_start, max_date])
    
    fig.update_layout(
        title={
            'text': 'Robot Harvest Speed',
            'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}
        },
        xaxis_title='',
        yaxis_title='seconds/tomato',
        height=400,
        hovermode='x unified',
        xaxis=dict(
            rangeslider=dict(visible=True, bgcolor=COLORS['surface']),
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True
        ),
        yaxis=dict(
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True,
            zeroline=False
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor=COLORS['border'],
            borderwidth=1
        ),
        margin=dict(l=60, r=40, t=80, b=60)
    )
    
    return fig

def create_harvest_weight_figure(selected_farms):
    """Chart 3: Harvest Weight (kg) Robot Scale over time - 7 day rolling average"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values
    chart_df = chart_df.dropna(subset=['Harvest \nWeight (kg)\nRobot Scale']).copy()
    chart_df = chart_df.sort_values('Start Datetime')
    
    fig = go.Figure()
    
    # If both farms are selected, show separate lines
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = chart_df[chart_df['Farm'] == farm].copy()
            # Calculate 7-day rolling average per farm
            farm_df['Rolling_Avg'] = farm_df['Harvest \nWeight (kg)\nRobot Scale'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=farm_df['Start Datetime'],
                y=farm_df['Rolling_Avg'],
                mode='lines',
                name=farm,
                line=dict(color=farm_colors.get(farm, COLORS['primary']), width=3)
            ))
    else:
        # Single farm or aggregated view
        chart_df['Rolling_Avg'] = chart_df['Harvest \nWeight (kg)\nRobot Scale'].rolling(window=7, min_periods=1).mean()
        
        fig.add_trace(go.Scatter(
            x=chart_df['Start Datetime'],
            y=chart_df['Rolling_Avg'],
            mode='lines',
            name='7-Day Average',
            line=dict(color=COLORS['secondary'], width=3),
            fill='tozeroy',
            fillcolor='rgba(64, 145, 108, 0.1)'
        ))
    
    # Set default x-axis range to last 4 weeks
    fig.update_xaxes(range=[default_start, max_date])
    
    fig.update_layout(
        title={
            'text': 'Harvest Weight',
            'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}
        },
        xaxis_title='',
        yaxis_title='Weight (kg)',
        height=400,
        hovermode='x unified',
        xaxis=dict(
            rangeslider=dict(visible=True, bgcolor=COLORS['surface']),
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True
        ),
        yaxis=dict(
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True,
            zeroline=False
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_fruit_weight_figure(selected_farms):
    """Chart 4: Average Fruit Weight over time - 7 day rolling average"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values
    chart_df = chart_df.dropna(subset=['Average Fruit Weight (g)']).copy()
    chart_df = chart_df.sort_values('Start Datetime')
    
    fig = go.Figure()
    
    # If both farms are selected, show separate lines
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = chart_df[chart_df['Farm'] == farm].copy()
            # Calculate 7-day rolling average per farm
            farm_df['Rolling_Avg'] = farm_df['Average Fruit Weight (g)'].rolling(window=7, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=farm_df['Start Datetime'],
                y=farm_df['Rolling_Avg'],
                mode='lines',
                name=farm,
                line=dict(color=farm_colors.get(farm, COLORS['primary']), width=3)
            ))
    else:
        # Single farm or aggregated view
        chart_df['Rolling_Avg'] = chart_df['Average Fruit Weight (g)'].rolling(window=7, min_periods=1).mean()
        
        fig.add_trace(go.Scatter(
            x=chart_df['Start Datetime'],
            y=chart_df['Rolling_Avg'],
            mode='lines',
            name='7-Day Average',
            line=dict(color=COLORS['accent'], width=3),
            fill='tozeroy',
            fillcolor='rgba(82, 183, 136, 0.1)'
        ))
    
    # Set default x-axis range to last 4 weeks
    fig.update_xaxes(range=[default_start, max_date])
    
    fig.update_layout(
        title={
            'text': 'Average Fruit Weight',
            'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}
        },
        xaxis_title='',
        yaxis_title='Weight (g)',
        height=400,
        hovermode='x unified',
        xaxis=dict(
            rangeslider=dict(visible=True, bgcolor=COLORS['surface']),
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True
        ),
        yaxis=dict(
            gridcolor=COLORS['grid'],
            linecolor=COLORS['border'],
            showline=True,
            zeroline=False
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

# Metrics Testing Chart Functions
# Metrics Testing Chart Functions
def create_metrics_figure_helper(selected_farms, column_name, title, yaxis_title, format_value_func, color=None):
    """Helper function to create metrics figures with farm separation"""
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    
    # Filter out zeros and NaN values
    df_baseline = df_baseline[df_baseline[column_name].notna()]
    df_baseline = df_baseline[df_baseline[column_name] > 0]
    
    fig = go.Figure()
    
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = df_baseline[df_baseline['Farm'] == farm].copy()
            daily_baseline = farm_df.groupby('Date').first().reset_index()
            
            all_dates_data = []
            for idx, row in daily_baseline.iterrows():
                date = row['Date']
                day_data = df_local[(df_local['Date'] == date) & (df_local['Farm'] == farm)].copy()
                
                baseline_branch = row['Branch']
                baseline_value = row[column_name]
                
                other_branches_info = []
                for _, other_row in day_data.iterrows():
                    if other_row['Baseline Run?'] == 'TRUE':
                        continue
                    other_branch = other_row['Branch']
                    other_value = other_row[column_name]
                    
                    if pd.notna(other_value) and other_value > 0:
                        pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                        sign = '+' if pct_change >= 0 else ''
                        other_branches_info.append(f"{other_branch}: {format_value_func(other_value)} ({sign}{pct_change:.1f}%)")
                
                hover_text = f"<b>Farm: {farm}</b><br>"
                hover_text += f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
                hover_text += f"Value: {format_value_func(baseline_value)}<br>"
                hover_text += f"<br><b>Other branches this day:</b><br>"
                hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
                
                all_dates_data.append(hover_text)
            
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(daily_baseline['Date']),
                y=daily_baseline[column_name],
                mode='markers',
                marker=dict(size=10, color=farm_colors.get(farm, COLORS['primary'])),
                name=farm,
                customdata=all_dates_data,
                hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
            ))
    else:
        daily_baseline = df_baseline.groupby('Date').first().reset_index()
        
        all_dates_data = []
        for idx, row in daily_baseline.iterrows():
            date = row['Date']
            day_data = df_local[df_local['Date'] == date].copy()
            
            baseline_branch = row['Branch']
            baseline_value = row[column_name]
            
            other_branches_info = []
            for _, other_row in day_data.iterrows():
                if other_row['Baseline Run?'] == 'TRUE':
                    continue
                other_branch = other_row['Branch']
                other_value = other_row[column_name]
                
                if pd.notna(other_value) and other_value > 0:
                    pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                    sign = '+' if pct_change >= 0 else ''
                    other_branches_info.append(f"{other_branch}: {format_value_func(other_value)} ({sign}{pct_change:.1f}%)")
            
            hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
            hover_text += f"Value: {format_value_func(baseline_value)}<br>"
            hover_text += f"<br><b>Other branches this day:</b><br>"
            hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
            
            all_dates_data.append(hover_text)
        
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(daily_baseline['Date']),
            y=daily_baseline[column_name],
            mode='markers',
            marker=dict(size=10, color=color or COLORS['primary']),
            name='Daily First Reading',
            customdata=all_dates_data,
            hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
        ))
    
    fig.update_layout(
        title={'text': title, 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title=yaxis_title,
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_ripe_fruits_figure(selected_farms):
    """Ripe Fruits Per Meter - baseline runs per date, separate lines per farm when both selected"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    
    # Filter out zeros and NaN values
    df_baseline = df_baseline[df_baseline['Ripe Fruits per meter'].notna()]
    df_baseline = df_baseline[df_baseline['Ripe Fruits per meter'] > 0]
    
    fig = go.Figure()
    
    # If both farms are selected, show separate lines
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = df_baseline[df_baseline['Farm'] == farm].copy()
            daily_baseline = farm_df.groupby('Date').first().reset_index()
            
            # Create hover text
            all_dates_data = []
            for idx, row in daily_baseline.iterrows():
                date = row['Date']
                day_data = df_local[(df_local['Date'] == date) & (df_local['Farm'] == farm)].copy()
                
                baseline_branch = row['Branch']
                baseline_value = row['Ripe Fruits per meter']
                
                other_branches_info = []
                for _, other_row in day_data.iterrows():
                    if other_row['Baseline Run?'] == 'TRUE':
                        continue
                    other_branch = other_row['Branch']
                    other_value = other_row['Ripe Fruits per meter']
                    
                    if pd.notna(other_value) and other_value > 0:
                        pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                        sign = '+' if pct_change >= 0 else ''
                        other_branches_info.append(f"{other_branch}: {other_value:.2f} ({sign}{pct_change:.1f}%)")
                
                hover_text = f"<b>Farm: {farm}</b><br>"
                hover_text += f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
                hover_text += f"Value: {baseline_value:.2f}<br>"
                hover_text += f"<br><b>Other branches this day:</b><br>"
                hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
                
                all_dates_data.append(hover_text)
            
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(daily_baseline['Date']),
                y=daily_baseline['Ripe Fruits per meter'],
                mode='markers',
                marker=dict(size=10, color=farm_colors.get(farm, COLORS['primary'])),
                name=farm,
                customdata=all_dates_data,
                hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
            ))
    else:
        # Single farm view
        daily_baseline = df_baseline.groupby('Date').first().reset_index()
        
        all_dates_data = []
        for idx, row in daily_baseline.iterrows():
            date = row['Date']
            day_data = df_local[df_local['Date'] == date].copy()
            
            baseline_branch = row['Branch']
            baseline_value = row['Ripe Fruits per meter']
            
            other_branches_info = []
            for _, other_row in day_data.iterrows():
                if other_row['Baseline Run?'] == 'TRUE':
                    continue
                other_branch = other_row['Branch']
                other_value = other_row['Ripe Fruits per meter']
                
                if pd.notna(other_value) and other_value > 0:
                    pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                    sign = '+' if pct_change >= 0 else ''
                    other_branches_info.append(f"{other_branch}: {other_value:.2f} ({sign}{pct_change:.1f}%)")
            
            hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
            hover_text += f"Value: {baseline_value:.2f}<br>"
            hover_text += f"<br><b>Other branches this day:</b><br>"
            hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
            
            all_dates_data.append(hover_text)
        
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(daily_baseline['Date']),
            y=daily_baseline['Ripe Fruits per meter'],
            mode='markers',
            marker=dict(size=10, color=COLORS['primary']),
            name='Daily First Reading',
            customdata=all_dates_data,
            hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
        ))
    
    fig.update_layout(
        title={'text': 'Ripe Fruits Per Meter (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='Ripe Fruits Per Meter',
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_recall_figure(selected_farms):
    """Recall with Questionable - baseline run per date"""
    return create_metrics_figure_helper(
        selected_farms,
        'Recall w/ Questionable',
        'Recall with Questionable (Daily)',
        'Recall',
        lambda v: f"{v:.2%}",
        COLORS['secondary']
    )

def create_metrics_precision_figure(selected_farms):
    """Precision with Questionable - baseline run per date"""
    return create_metrics_figure_helper(
        selected_farms,
        'Precision w/ Questionable',
        'Precision with Questionable (Daily)',
        'Precision',
        lambda v: f"{v:.2%}",
        COLORS['accent']
    )

def create_metrics_harvest_speed_figure(selected_farms):
    """Real Harvest Speed - baseline run per date"""
    return create_metrics_figure_helper(
        selected_farms,
        'Real Harvest Speed',
        'Real Harvest Speed (Daily)',
        'seconds/tomato',
        lambda v: f"{v:.2f}",
        COLORS['primary']
    )

def create_metrics_drop_rate_figure(selected_farms):
    """Drop Rate - baseline run per date"""
    return create_metrics_figure_helper(
        selected_farms,
        'Drop Rate',
        'Drop Rate (Daily)',
        'Drop Rate',
        lambda v: f"{v:.2%}",
        COLORS['secondary']
    )

def create_metrics_savings_figure(selected_farms):
    """Savings Relative to Status Quo - based on H&A Business Case model"""
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    
    # Filter out rows with missing data
    df_baseline = df_baseline[
        df_baseline['Real Harvest Speed'].notna() &
        df_baseline['Recall w/ Questionable'].notna() &
        df_baseline['Precision w/ Questionable'].notna()
    ].copy()
    
    
    fruit_weight = 11.0 
    weeks_harvested = 40  
    person_harvesting_rate=50
    hourly_wage=22
    harvesting_cost_per_kg = hourly_wage / person_harvesting_rate
    annual_production = 33
    farm_size=4.2 #ha
    annual_production_total= farm_size*annual_production*10000 
    additional_human_costs=0
    total_harvesting_cost_per_kg = harvesting_cost_per_kg + additional_human_costs
    total_farm_human_cost= total_harvesting_cost_per_kg * annual_production_total
    robots_per_farm=5.114
    equivalent_harvesting_cost_human_per_robot= total_farm_human_cost/robots_per_farm
    robot_hours_per_day=22
   
    
    # Calculate savings for each day
    savings_data = []
    
    for idx, row in df_baseline.iterrows():
        date = row['Date']
        
        # Map metrics to Excel cells
        harvesting_speed = row['Real Harvest Speed']  
        recall_with_questionable = row['Recall w/ Questionable']  
        precision_with_questionable = row['Precision w/ Questionable']   
        daily_robot_capacity_kg=(fruit_weight/harvesting_speed*60*60*robot_hours_per_day)/1000
        weekly_robot_capacity_kg=daily_robot_capacity_kg*7
        daily_human_sweeping=(daily_robot_capacity_kg/recall_with_questionable)*(1/recall_with_questionable)
        weekly_human_sweeping=daily_human_sweeping*7
        total_robot_harvested=weekly_robot_capacity_kg*weeks_harvested
        total_human_swept=weekly_human_sweeping*weeks_harvested
        total_harvested=total_robot_harvested+total_human_swept

        sweeping_speed_reduction=.25
        sweeping_cost=total_harvesting_cost_per_kg*(1+sweeping_speed_reduction)

        robot_cost=95000

        total_human_sweeping_cost=total_human_swept*sweeping_cost
        operator_wage=22
        robots_overseen=5.1
        daily_operator_time=6
        annual_operator_cost=(operator_wage*daily_operator_time*7*weeks_harvested)/robots_overseen
        
        total_costs_robot_per_year=total_human_sweeping_cost+robot_cost+annual_operator_cost
        

        human_fruit_drop=3.5/100
        robot_fruit_drop=.5/100
        robot_greens_lost=total_harvested*(robot_fruit_drop+(1-precision_with_questionable))
        human_greens_lost=total_harvested*(human_fruit_drop)


        market_price_per_kg=5
        discounting_factor=.8

        robot_opportunity_costs_of_greens_lost=robot_greens_lost*market_price_per_kg*discounting_factor
        human_opportunity_costs_of_greens_lost=human_greens_lost*market_price_per_kg*discounting_factor 
        print('robot_opportunity_costs_of_greens_lost',robot_opportunity_costs_of_greens_lost)
        print('human_opportunity_costs_of_greens_lost',human_opportunity_costs_of_greens_lost)

        print('total_costs_robot_per_year',total_costs_robot_per_year)
        print('equivalent_harvesting_cost_human_per_robot',equivalent_harvesting_cost_human_per_robot)

        total_costs_robot_per_year_with_waste=total_costs_robot_per_year+robot_opportunity_costs_of_greens_lost
        total_costs_human_per_year_with_waste=equivalent_harvesting_cost_human_per_robot+human_opportunity_costs_of_greens_lost

        percentage_savings=(total_costs_human_per_year_with_waste-total_costs_robot_per_year_with_waste)/total_costs_human_per_year_with_waste






        savings_data.append({
            'date': date,
            'farm': row['Farm'],
            'savings': percentage_savings,
            'recall': recall_with_questionable,
            'precision': precision_with_questionable,
            'speed': harvesting_speed
        })
    
    if not savings_data:
        # Return empty figure
        fig = go.Figure()
        fig.update_layout(
            title={'text': 'Savings Relative to Status Quo (Daily)', 'font': {'size': 18}},
            annotations=[{'text': 'No data available', 'showarrow': False, 'font': {'size': 20}}]
        )
        return fig
    
    df_savings = pd.DataFrame(savings_data)
    df_savings['date'] = pd.to_datetime(df_savings['date'])
    
    fig = go.Figure()
    
    if len(selected_farms) > 1:
        farm_colors = {
            'Costa': COLORS['primary'],
            'H&A': COLORS['secondary']
        }
        
        for farm in selected_farms:
            farm_df = df_savings[df_savings['farm'] == farm].copy()
            if not farm_df.empty:
                fig.add_trace(go.Scatter(
                    x=farm_df['date'],
                    y=farm_df['savings'] * 100,  # Convert to percentage
                    mode='markers+lines',
                    marker=dict(size=8, color=farm_colors.get(farm, COLORS['primary'])),
                    line=dict(color=farm_colors.get(farm, COLORS['primary']), width=2),
                    name=farm
                ))
    else:
        fig.add_trace(go.Scatter(
            x=df_savings['date'],
            y=df_savings['savings'] * 100,  # Convert to percentage
            mode='markers+lines',
            marker=dict(size=8, color=COLORS['primary']),
            line=dict(color=COLORS['primary'], width=2),
            name='Savings'
        ))
    
    fig.update_layout(
        title={'text': 'Savings Relative to Status Quo (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='Savings (%)',
        height=400,
        hovermode='x unified',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=True),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

# Callback for Business Case Calculator
@callback(
    Output('calculator-result', 'children'),
    Output('calculator-result', 'style'),
    Input('input-fruit-weight', 'value'),
    Input('input-harvest-time', 'value'),
    Input('input-annual-production', 'value'),
    Input('input-base-cost', 'value'),
    Input('input-robot-speed', 'value'),
    Input('input-recall', 'value'),
    Input('input-precision', 'value'),
    Input('input-fruitdrop-human', 'value'),
    Input('input-fruitdrop-robot', 'value'),
    Input('input-b80', 'value'),
    Input('input-b81', 'value')
)
def calculate_savings(fruit_weight, harvest_time, annual_production, base_cost, 
                     robot_speed, recall, precision, fruitdrop_human, fruitdrop_robot, 
                     b80, b81):
    try:
        # Business case calculation
        # B30 = Daily Robot Harvesting capacity
        B30 = (fruit_weight / robot_speed * 60 * 60 * harvest_time) / 1000
        
        # B78 = Cost savings per robot from reduced fruit drop
        B78 = (fruitdrop_robot + precision * 100 - fruitdrop_human) * b80 * b81
        
        # Calculate savings
        base_total_cost = annual_production * base_cost
        efficiency_factor = recall  # Use recall as efficiency
        
        # Adjusted cost based on efficiency
        adjusted_cost = base_total_cost * (1 - efficiency_factor * 0.5)  # Max 50% savings at 100% recall
        
        # Calculate savings
        savings = (base_total_cost - adjusted_cost) / base_total_cost
        
        # Add B78 impact
        savings += B78 / base_total_cost if base_total_cost > 0 else 0
        
        # Convert to percentage
        savings_pct = savings * 100
        
        # Determine color
        if savings_pct < -5:
            bg_color = '#ffebee'  # Light red
            text_color = '#c62828'  # Dark red
        elif savings_pct < 0:
            bg_color = '#fff9c4'  # Light yellow
            text_color = '#f57f17'  # Dark yellow
        elif savings_pct < 10:
            bg_color = '#e8f5e9'  # Light green
            text_color = '#2e7d32'  # Dark green
        else:
            bg_color = '#c8e6c9'  # Medium green
            text_color = '#1b5e20'  # Darker green
        
        result_text = f"{savings_pct:+.2f}%"
        
        result_style = {
            'fontSize': '64px',
            'fontWeight': '700',
            'textAlign': 'center',
            'padding': '40px',
            'borderRadius': '12px',
            'boxShadow': '0 4px 12px rgba(0, 0, 0, 0.1)',
            'backgroundColor': bg_color,
            'color': text_color
        }
        
        return result_text, result_style
        
    except Exception as e:
        return f"Error: {str(e)}", {
            'fontSize': '20px',
            'textAlign': 'center',
            'padding': '40px',
            'color': '#d32f2f'
        }

# Run the app
if __name__ == '__main__':
    print("\n" + "="*60)
    print("Dashboard starting...")
    print("Open your browser and go to: http://127.0.0.1:8050")
    print("="*60 + "\n")
    app.run(debug=True)

# Expose server for deployment
server = app.server
