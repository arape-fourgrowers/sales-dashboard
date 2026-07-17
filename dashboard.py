import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

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
        ], style={'padding': '32px 40px', 'maxWidth': '1400px', 'margin': '0 auto', 'background': COLORS['surface']})

# Create static figures with default 4-week view
def create_ripe_fruits_figure(selected_farms):
    """Chart 1: Ripe Fruits per Meter over time (all robots grouped) - 7 day rolling average"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values
    chart_df = chart_df.dropna(subset=['Ripe Fruits per Meter']).copy()
    chart_df = chart_df.sort_values('Start Datetime')
    
    # Calculate 7-day rolling average
    chart_df['Rolling_Avg'] = chart_df['Ripe Fruits per Meter'].rolling(window=7, min_periods=1).mean()
    
    fig = go.Figure()
    
    # Add rolling average line
    fig.add_trace(go.Scatter(
        x=chart_df['Start Datetime'],
        y=chart_df['Rolling_Avg'],
        mode='lines',
        name='7-Day Average',
        line=dict(color=COLORS['primary'], width=3),
        fill='tozeroy',
        fillcolor='rgba(45, 106, 79, 0.1)'
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
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_harvest_speed_figure(selected_farms):
    """Chart 2: Robot Harvest Speed over time by robot - 7 day rolling average"""
    # Filter by selected farms
    chart_df = df[df['Farm'].isin(selected_farms)].copy() if selected_farms else df.copy()
    
    # Remove NaN values and filter out invalid robot numbers
    chart_df = chart_df.dropna(subset=['Robot Harvest Speed', 'AMA Number']).copy()
    chart_df = chart_df[chart_df['AMA Number'] > 0]
    chart_df = chart_df.sort_values('Start Datetime')
    
    # Convert AMA Number to string for better legend
    chart_df['Robot'] = 'Robot ' + chart_df['AMA Number'].astype(int).astype(str)
    
    fig = go.Figure()
    
    # FourGrowers green color palette
    robot_colors = [
        COLORS['primary'],      # Forest green
        COLORS['secondary'],    # Medium green
        COLORS['accent'],       # Light green
        '#74c69d',              # Lighter green
        '#95d5b2',              # Even lighter
        '#b7e4c7',              # Pale green
        '#d8f3dc'               # Very pale
    ]
    
    # Calculate 7-day rolling average for each robot
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
    
    # Calculate 7-day rolling average
    chart_df['Rolling_Avg'] = chart_df['Harvest \nWeight (kg)\nRobot Scale'].rolling(window=7, min_periods=1).mean()
    
    fig = go.Figure()
    
    # Add rolling average line
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
    
    # Calculate 7-day rolling average
    chart_df['Rolling_Avg'] = chart_df['Average Fruit Weight (g)'].rolling(window=7, min_periods=1).mean()
    
    fig = go.Figure()
    
    # Add rolling average line
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
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

# Metrics Testing Chart Functions
def create_metrics_ripe_fruits_figure(selected_farms):
    """Ripe Fruits Per Meter - baseline runs per date, clickable to show all points for that day"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    
    # Get baseline run per date
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    daily_baseline = df_baseline.groupby('Date').first().reset_index()
    
    # Filter out zeros and NaN values
    daily_baseline = daily_baseline[daily_baseline['Ripe Fruits per meter'].notna()]
    daily_baseline = daily_baseline[daily_baseline['Ripe Fruits per meter'] > 0]
    
    # Get all data for each date for hover info
    all_dates_data = []
    for idx, row in daily_baseline.iterrows():
        date = row['Date']
        day_data = df_local[df_local['Date'] == date].copy()
        
        # Get the branch for this baseline data point
        baseline_branch = row['Branch']
        baseline_value = row['Ripe Fruits per meter']
        
        # Get all other branches for this day with their values and percentage differences
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
    
    fig = go.Figure()
    
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
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_recall_figure(selected_farms):
    """Recall with Questionable - baseline run per date"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    daily_baseline = df_baseline.groupby('Date').first().reset_index()
    
    # Filter out zeros and NaN values
    daily_baseline = daily_baseline[daily_baseline['Recall w/ Questionable'].notna()]
    daily_baseline = daily_baseline[daily_baseline['Recall w/ Questionable'] > 0]
    
    all_dates_data = []
    for idx, row in daily_baseline.iterrows():
        date = row['Date']
        day_data = df_local[df_local['Date'] == date].copy()
        
        baseline_branch = row['Branch']
        baseline_value = row['Recall w/ Questionable']
        
        other_branches_info = []
        for _, other_row in day_data.iterrows():
            if other_row['Baseline Run?'] == 'TRUE':
                continue
            other_branch = other_row['Branch']
            other_value = other_row['Recall w/ Questionable']
            
            if pd.notna(other_value) and other_value > 0:
                pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                sign = '+' if pct_change >= 0 else ''
                other_branches_info.append(f"{other_branch}: {other_value:.2%} ({sign}{pct_change:.1f}%)")
        
        hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
        hover_text += f"Value: {baseline_value:.2%}<br>"
        hover_text += f"<br><b>Other branches this day:</b><br>"
        hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
        
        all_dates_data.append(hover_text)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(daily_baseline['Date']),
        y=daily_baseline['Recall w/ Questionable'],
        mode='markers',
        marker=dict(size=10, color=COLORS['secondary']),
        name='Daily First Reading',
        customdata=all_dates_data,
        hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
    ))
    
    fig.update_layout(
        title={'text': 'Recall with Questionable (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='Recall',
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_precision_figure(selected_farms):
    """Precision with Questionable - baseline run per date"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    daily_baseline = df_baseline.groupby('Date').first().reset_index()
    
    # Filter out zeros and NaN values
    daily_baseline = daily_baseline[daily_baseline['Precision w/ Questionable'].notna()]
    daily_baseline = daily_baseline[daily_baseline['Precision w/ Questionable'] > 0]
    
    all_dates_data = []
    for idx, row in daily_baseline.iterrows():
        date = row['Date']
        day_data = df_local[df_local['Date'] == date].copy()
        
        baseline_branch = row['Branch']
        baseline_value = row['Precision w/ Questionable']
        
        other_branches_info = []
        for _, other_row in day_data.iterrows():
            if other_row['Baseline Run?'] == 'TRUE':
                continue
            other_branch = other_row['Branch']
            other_value = other_row['Precision w/ Questionable']
            
            if pd.notna(other_value) and other_value > 0:
                pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                sign = '+' if pct_change >= 0 else ''
                other_branches_info.append(f"{other_branch}: {other_value:.2%} ({sign}{pct_change:.1f}%)")
        
        hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
        hover_text += f"Value: {baseline_value:.2%}<br>"
        hover_text += f"<br><b>Other branches this day:</b><br>"
        hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
        
        all_dates_data.append(hover_text)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(daily_baseline['Date']),
        y=daily_baseline['Precision w/ Questionable'],
        mode='markers',
        marker=dict(size=10, color=COLORS['accent']),
        name='Daily First Reading',
        customdata=all_dates_data,
        hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
    ))
    
    fig.update_layout(
        title={'text': 'Precision with Questionable (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='Precision',
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_harvest_speed_figure(selected_farms):
    """Real Harvest Speed - baseline run per date"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    daily_baseline = df_baseline.groupby('Date').first().reset_index()
    
    # Filter out zeros and NaN values
    daily_baseline = daily_baseline[daily_baseline['Real Harvest Speed'].notna()]
    daily_baseline = daily_baseline[daily_baseline['Real Harvest Speed'] > 0]
    
    all_dates_data = []
    for idx, row in daily_baseline.iterrows():
        date = row['Date']
        day_data = df_local[df_local['Date'] == date].copy()
        
        baseline_branch = row['Branch']
        baseline_value = row['Real Harvest Speed']
        
        other_branches_info = []
        for _, other_row in day_data.iterrows():
            if other_row['Baseline Run?'] == 'TRUE':
                continue
            other_branch = other_row['Branch']
            other_value = other_row['Real Harvest Speed']
            
            if pd.notna(other_value) and other_value > 0:
                pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                sign = '+' if pct_change >= 0 else ''
                other_branches_info.append(f"{other_branch}: {other_value:.2f} ({sign}{pct_change:.1f}%)")
        
        hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
        hover_text += f"Value: {baseline_value:.2f}<br>"
        hover_text += f"<br><b>Other branches this day:</b><br>"
        hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
        
        all_dates_data.append(hover_text)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(daily_baseline['Date']),
        y=daily_baseline['Real Harvest Speed'],
        mode='markers',
        marker=dict(size=10, color=COLORS['primary']),
        name='Daily First Reading',
        customdata=all_dates_data,
        hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
    ))
    
    fig.update_layout(
        title={'text': 'Real Harvest Speed (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='seconds/tomato',
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

def create_metrics_drop_rate_figure(selected_farms):
    """Drop Rate - baseline run per date"""
    # Filter by selected farms
    df_local = df_metrics[df_metrics['Farm'].isin(selected_farms)].copy() if selected_farms else df_metrics.copy()
    df_local['Date'] = df_local['Start Datetime'].dt.date
    df_baseline = df_local[df_local['Baseline Run?'] == 'TRUE'].copy()
    daily_baseline = df_baseline.groupby('Date').first().reset_index()
    
    # Filter out zeros and NaN values
    daily_baseline = daily_baseline[daily_baseline['Drop Rate'].notna()]
    daily_baseline = daily_baseline[daily_baseline['Drop Rate'] > 0]
    
    all_dates_data = []
    for idx, row in daily_baseline.iterrows():
        date = row['Date']
        day_data = df_local[df_local['Date'] == date].copy()
        
        baseline_branch = row['Branch']
        baseline_value = row['Drop Rate']
        
        other_branches_info = []
        for _, other_row in day_data.iterrows():
            if other_row['Baseline Run?'] == 'TRUE':
                continue
            other_branch = other_row['Branch']
            other_value = other_row['Drop Rate']
            
            if pd.notna(other_value) and other_value > 0:
                pct_change = ((other_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 0
                sign = '+' if pct_change >= 0 else ''
                other_branches_info.append(f"{other_branch}: {other_value:.2%} ({sign}{pct_change:.1f}%)")
        
        hover_text = f"<b>Branch: {baseline_branch} (Baseline)</b><br>"
        hover_text += f"Value: {baseline_value:.2%}<br>"
        hover_text += f"<br><b>Other branches this day:</b><br>"
        hover_text += "<br>".join(other_branches_info) if other_branches_info else "None"
        
        all_dates_data.append(hover_text)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(daily_baseline['Date']),
        y=daily_baseline['Drop Rate'],
        mode='markers',
        marker=dict(size=10, color=COLORS['secondary']),
        name='Daily First Reading',
        customdata=all_dates_data,
        hovertemplate='<b>Date: %{x|%Y-%m-%d}</b><br>%{customdata}<extra></extra>'
    ))
    
    fig.update_layout(
        title={'text': 'Drop Rate (Daily)', 'font': {'size': 18, 'color': COLORS['text'], 'family': 'system-ui'}},
        xaxis_title='',
        yaxis_title='Drop Rate',
        height=400,
        hovermode='closest',
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        font={'color': COLORS['text'], 'family': 'system-ui'},
        xaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True),
        yaxis=dict(gridcolor=COLORS['grid'], linecolor=COLORS['border'], showline=True, zeroline=False),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig

# Run the app
if __name__ == '__main__':
    print("\n" + "="*60)
    print("Dashboard starting...")
    print("Open your browser and go to: http://127.0.0.1:8050")
    print("="*60 + "\n")
    app.run(debug=True)

# Expose server for deployment
server = app.server
