import streamlit as st
import pandas as pd
import os
import plotly.express as px
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import base64
import io
import json
from pathlib import Path
import openpyxl  # Add this import for Excel handling

# Add database imports with error handling
import mysql.connector
import sqlalchemy
import sqlite3
try:
    import psycopg2
except ImportError:
    # Create a placeholder for PostgreSQL functionality
    class PostgresqlNotInstalled:
        def __init__(self, *args, **kwargs):
            raise ImportError("psycopg2 is not installed. PostgreSQL features will not be available.")
    
    psycopg2 = PostgresqlNotInstalled
    st.warning("PostgreSQL driver (psycopg2) is not installed. PostgreSQL features will not be available.")

# Set page configuration
st.set_page_config(
    page_title="Test Station Maintenance Control",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Helper function to get database config path
def get_db_config_path():
    """Get the path to database configuration file"""
    possible_paths = [
        Path(get_app_dir()) / "config" / "database_config.json",
        Path("config/database_config.json"),
        Path("./config/database_config.json")
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None

# Helper function to load database configuration
def load_database_config():
    """Load database configuration from JSON file"""
    config_path = get_db_config_path()
    
    if not config_path:
        st.warning("Database configuration file not found. Will use CSV fallback.")
        return None
    
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading database configuration: {e}")
        return None

# Function to connect to database and fetch data
def load_data_from_database():
    """Load data from database defined in configuration"""
    db_config = load_database_config()
    
    if not db_config:
        return None, "Database configuration not found"
    
    conn = None  # Initialize conn outside try block
    try:
        conn_params = db_config.get("connection", {})
        if not conn_params:
            return None, "No connection parameters found in configuration"
            
        db_type = conn_params.get("type", "").lower()
        
        # Get connection based on database type
        if db_type == "mysql":
            # Add specific error handling for MySQL connection
            try:
                conn = mysql.connector.connect(
                    host=conn_params.get("host"),
                    port=conn_params.get("port", 3306),
                    user=conn_params.get("user"),
                    password=conn_params.get("password"),
                    database=conn_params.get("database")
                )
            except mysql.connector.Error as err:
                error_message = f"MySQL Connection Error: {err}"
                if err.errno == 1045:  # Access denied error code
                    error_message += "\n\nPlease check:\n1. Database username and password in config.\n2. Database host permissions (ensure the user can connect from this app's IP address)."
                return None, error_message
                
        elif db_type == "postgresql":
            # Add specific error handling for PostgreSQL connection
            try:
                conn = psycopg2.connect(
                    host=conn_params.get("host"),
                    port=conn_params.get("port", 5432),
                    user=conn_params.get("user"),
                    password=conn_params.get("password"),
                    database=conn_params.get("database")
                )
            except psycopg2.Error as err:
                # Check for common connection errors (e.g., authentication failure)
                error_message = f"PostgreSQL Connection Error: {err}"
                return None, error_message
                
        elif db_type == "sqlite":
            # Add specific error handling for SQLite connection
            try:
                # For SQLite, the host parameter is used as the file path
                db_path = conn_params.get("host")
                if not db_path:
                    return None, "SQLite database path not specified in configuration."
                conn = sqlite3.connect(db_path)
            except sqlite3.Error as err:
                return None, f"SQLite Connection Error: {err}"
        else:
            return None, f"Unsupported database type: {db_type}"
        
        if not conn:
            return None, "Failed to establish database connection (check configuration and network)."
            
        # Add debugging information
        print(f"Database connection parameters: {conn_params}")
        
        # Get query from config
        query_config = db_config.get("query", {})
        if not query_config:
            return None, "No query configuration found"
            
        query = query_config.get("custom_query") if query_config.get("custom_query_enabled", False) else query_config.get("main_query")
        
        if not query:
            return None, "No query specified in configuration"
        
        # Execute query and get results
        df = pd.read_sql(query, conn)
        
        # Close connection
        conn.close()
        conn = None  # Ensure conn is None after closing
        
        if df.empty:
            return None, "Query returned no results"
        
        # Apply column mappings
        column_mapping = db_config.get("column_mapping", {})
        if column_mapping:
            # Create a new DataFrame with app's expected column names
            result_dict = {}
            for app_col, db_col in column_mapping.items():
                if db_col in df.columns:
                    result_dict[app_col] = df[db_col]
                else:
                    print(f"Warning: Column {db_col} not found in query results")
            
            # Create result DataFrame with mapped columns
            if result_dict:
                result_df = pd.DataFrame(result_dict)
            else:
                return None, "No columns could be mapped from the query results"
        else:
            # If no mapping provided, use the DataFrame as is
            result_df = df
        
        # Parse dates
        result_df = parse_date_column(result_df, 'testDate')
        if 'lastMaintenance' in result_df.columns:
            result_df = parse_date_column(result_df, 'lastMaintenance')
        
        # Calculate maintenance due if needed
        result_df = calculate_maintenance_due(result_df)
        
        return result_df, None
        
    except Exception as e:
        # General exception handler
        error_type = type(e).__name__
        error_details = str(e)
        # Provide more context if possible
        if "Access denied" in error_details or "authentication failed" in error_details:
            error_message = f"Error loading data from database ({error_type}): {error_details}\n\nPlease check database credentials and host permissions."
        else:
            error_message = f"Error loading data from database ({error_type}): {error_details}"
        
        # Ensure connection is closed even if error occurs later
        if conn:
            try:
                conn.close()
            except Exception as close_err:
                print(f"Error closing database connection: {close_err}")  # Log closing error
        return None, error_message

# Modified function to try loading data from database only
def try_load_default_data():
    """Load data from database only"""
    # Load directly from database, no fallback
    df, error = load_data_from_database()
    
    if df is not None:
        return df, None
    
    # If we get here, database connection failed
    return None, f"Failed to load data from database: {error}"

# Helper function to convert string dates to datetime objects
def parse_date_column(df, date_column='testDate'):
    """Parse string date column to datetime objects"""
    if date_column in df.columns:
        try:
            df[date_column] = pd.to_datetime(df[date_column])
            return df
        except Exception as e:
            st.warning(f"Could not parse date column {date_column}: {e}")
    return df

# Helper functions
def load_sample_data():
    """Load sample data when no file is uploaded"""
    data = {
        'stationName': ["Station A", "Station B", "Station A", "Station C", "Station B"],
        'result': ["PASSED", "FAILED", "PASSED", "SCRAP", "PASSED"],
        'slot': ["Slot 1", "Slot 2", "Slot 3", "Slot 1", "Slot 2"],
        'testDate': ["2023-08-01", "2023-08-02", "2023-08-03", "2023-08-04", "2023-08-05"],
        'lastMaintenance': ["2023-07-15", "2023-07-10", "2023-07-20", "2023-07-05", "2023-07-25"],
        'cycleCount': [120, 230, 95, 310, 180],
        'maintenanceDue': [30, 5, 15, -2, 20]  # Days until maintenance is due (negative = overdue)
    }
    df = pd.DataFrame(data)
    # Convert date columns to datetime
    for col in ['testDate', 'lastMaintenance']:
        df[col] = pd.to_datetime(df[col])
    return df

def get_app_dir():
    """Get the application directory in a way that works locally and on Streamlit Cloud"""
    try:
        # When running locally
        return Path(os.path.dirname(__file__))
    except:
        # When running on Streamlit Cloud
        return Path.cwd()

def try_load_default_csv():
    """Legacy function, replaced by try_load_default_data"""
    return try_load_default_data()

def parse_uploaded_csv(uploaded_file):
    """Parse an uploaded CSV file"""
    try:
        df = pd.read_csv(uploaded_file)
        # Create a dictionary for the result dataframe
        result_dict = {
            'stationName': df.iloc[:, 5],
            'result': df.iloc[:, 6],
            'slot': df.iloc[:, 7],
            'testDate': df.iloc[:, 8]
        }
        
        # Look for maintenance columns (could be in different positions)
        for col_name in df.columns:
            if 'lastMaintenance' in col_name.lower():
                result_dict['lastMaintenance'] = df[col_name]
            elif 'maintenancedue' in col_name.lower():
                result_dict['maintenanceDue'] = df[col_name]
            elif 'cyclecount' in col_name.lower():
                result_dict['cycleCount'] = df[col_name]
        
        # Create dataframe from the extracted columns
        result_df = pd.DataFrame(result_dict)
        
        # Convert date columns to datetime
        result_df = parse_date_column(result_df, 'testDate')
        if 'lastMaintenance' in result_df.columns:
            result_df = parse_date_column(result_df, 'lastMaintenance')
            
        # Calculate maintenance due dates if needed
        result_df = calculate_maintenance_due(result_df)
        
        return result_df, None
    except Exception as e:
        return None, f"Error parsing CSV: {str(e)}"

def create_summary_metrics(df):
    """Create summary metrics from the dataframe"""
    total_tests = len(df)
    passed_tests = df[df['result'].str.contains('PASSED', case=False, na=False)].shape[0]
    failed_tests = total_tests - passed_tests
    pass_rate = round((passed_tests / total_tests) * 100) if total_tests > 0 else 0
    
    # Add maintenance metrics
    if 'maintenanceDue' in df.columns:
        overdue = df[df['maintenanceDue'] < 0].shape[0]
        due_soon = df[(df['maintenanceDue'] >= 0) & (df['maintenanceDue'] <= 7)].shape[0]
        ok_status = df[df['maintenanceDue'] > 7].shape[0]
        return total_tests, passed_tests, failed_tests, pass_rate, overdue, due_soon, ok_status
    
    return total_tests, passed_tests, failed_tests, pass_rate

def create_station_chart(df):
    """Create a bar chart of pass/fail by station"""
    station_results = df.groupby('stationName').apply(
        lambda x: pd.Series({
            'Passed': sum(x['result'].str.contains('PASSED', case=False, na=False)),
            'Failed': len(x) - sum(x['result'].str.contains('PASSED', case=False, na=False))
        }),
        include_groups=False
    ).reset_index()
    
    # Melt the dataframe for easier plotting
    station_results_melted = station_results.melt(
        id_vars=['stationName'],
        value_vars=['Passed', 'Failed'],
        var_name='Status',
        value_name='Count'
    )
    
    # Use brand colors for the chart
    fig = px.bar(
        station_results_melted, 
        x='stationName', 
        y='Count',
        color='Status',
        barmode='group',
        title='Test Results by Station',
        color_discrete_map={
            'Passed': brand_config.get('colors', {}).get('secondary', 'green'), 
            'Failed': brand_config.get('colors', {}).get('danger', 'red')
        },
        labels={'stationName': 'Station Name', 'Count': 'Number of Tests'}
    )
    
    # Update overall chart styling
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        title_font_color=brand_config.get('css_elements', {}).get('heading_color', '#000'),
        font_family=brand_config.get('fonts', {}).get('primary_font', 'sans-serif')
    )
    
    return fig

def create_maintenance_chart(df):
    """Create chart showing maintenance status by station"""
    if 'maintenanceDue' not in df.columns:
        return None
        
    # Create maintenance status categories
    df['maintenance_status'] = 'OK'
    df.loc[df['maintenanceDue'] <= 7, 'maintenance_status'] = 'Due Soon'
    df.loc[df['maintenanceDue'] < 0, 'maintenance_status'] = 'Overdue'
    
    # Group by station and maintenance status
    station_maintenance = df.groupby(['stationName', 'maintenance_status']).size().reset_index(name='count')
    
    # Create the chart
    fig = px.bar(
        station_maintenance, 
        x='stationName', 
        y='count',
        color='maintenance_status',
        barmode='group',
        title='Maintenance Status by Station',
        color_discrete_map={
            'OK': brand_config.get('colors', {}).get('secondary', 'green'), 
            'Due Soon': brand_config.get('colors', {}).get('warning', 'orange'),
            'Overdue': brand_config.get('colors', {}).get('danger', 'red')
        },
        labels={'stationName': 'Station Name', 'count': 'Number of Slots', 'maintenance_status': 'Status'}
    )
    
    # Update layout
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        title_font_color=brand_config.get('css_elements', {}).get('heading_color', '#000'),
        font_family=brand_config.get('fonts', {}).get('primary_font', 'sans-serif')
    )
    
    return fig

def load_brand_config():
    """Load brand configuration from file or use default if not available"""
    try:
        # Try multiple possible locations for the config file
        possible_paths = [
            Path(get_app_dir()) / "assets" / "brand_config.json",
            Path("assets/brand_config.json"),
            Path("./assets/brand_config.json")
        ]
        
        for path in possible_paths:
            if path.exists():
                with open(path, "r") as f:
                    return json.load(f)
        
        # If no config file found, return default config
        st.warning("Brand config not found, using default configuration")
        return {
            "company_information": {"company_name": "Test Station Maintenance Control"},
            "colors": {
                "primary": "#006161",
                "secondary": "#28a745",
                "accent": "#0077b6",
                "danger": "#dc3545",
                "warning": "#ffc107",
                "neutral": "#6c757d",
                "light": "#f8f9fa",
                "dark": "#212529"
            },
            "fonts": {"primary_font": "Roboto"},
            "css_elements": {
                "body_color": "#212529",
                "heading_color": "#212529",
                "metrics_box_bg": "#F1F3F4",
                "footer_bg": "#F1F3F4"
            },
            "styling": {
                "table_header_bg": "#006161",
                "table_header_text": "#FFFFFF",
                "table_stripe_color": "#F8F9FA"
            }
        }
    except Exception as e:
        st.warning(f"Could not load brand config: {e}. Using default configuration.")
        return {}

def get_image_as_base64(image_path):
    """Convert an image to base64 for embedding in HTML/CSS"""
    try:
        # Handle both string and Path objects
        image_path = Path(image_path) if not isinstance(image_path, Path) else image_path
        
        if image_path.exists():
            with open(image_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode('utf-8')
        return ""
    except Exception as e:
        st.warning(f"Error loading image {image_path}: {e}")
        return ""

# Load brand configuration
brand_config = load_brand_config()

# Primary color for styling elements
primary_color = brand_config.get("colors", {}).get("primary", "#006161")

# Create comprehensive CSS based on brand config
if brand_config:
    # Try to load the logo for header
    logo_path = None
    possible_logo_paths = [
        Path(get_app_dir()) / brand_config.get("assets", {}).get("logo_path", ""),
        Path("assets") / "logo.png",
        Path("./assets/logo.png")
    ]
    
    for path in possible_logo_paths:
        if path.exists():
            logo_path = path
            break
            
    logo_base64 = get_image_as_base64(logo_path) if logo_path else ""
    
    primary_color = brand_config.get("colors", {}).get("primary", "#006161")
    secondary_color = brand_config.get("colors", {}).get("secondary", "#28a745")
    accent_color = brand_config.get("colors", {}).get("accent", "#0077b6")
    danger_color = brand_config.get("colors", {}).get("danger", "#dc3545")
    neutral_color = brand_config.get("colors", {}).get("neutral", "#6c757d")
    light_color = brand_config.get("colors", {}).get("light", "#f8f9fa")
    dark_color = brand_config.get("colors", {}).get("dark", "#212529")
    
    primary_font = brand_config.get("fonts", {}).get("primary_font", "Roboto")
    
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family={primary_font.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
    
    /* Base elements */
    body, .stApp {{
        font-family: '{primary_font}', sans-serif !important;
        color: {brand_config.get("css_elements", {}).get("body_color", "#212529")};
        background-color: #f8f9fa;
    }}
    
    h1, h2, h3, h4, h5, h6 {{
        color: {brand_config.get("css_elements", {}).get("heading_color", "#000")} !important;
        font-family: '{primary_font}', sans-serif !important;
        font-weight: 600;
    }}
    
    /* Modern card design */
    .card {{
        background-color: white;
        border-radius: 10px;
        padding: 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
        transition: transform 0.3s ease;
    }}
    
    .card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }}
    
    .card-header {{
        border-bottom: 1px solid #eee;
        padding-bottom: 0.8rem;
        margin-bottom: 1rem;
        font-weight: 600;
    }}
    
    /* Status indicators */
    .status-badge {{
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 50px;
        color: white;
        font-weight: 500;
        font-size: 0.9rem;
    }}
    
    .status-ok {{ background-color: {brand_config.get("colors", {}).get("secondary", "green")}; }}
    .status-warning {{ background-color: {brand_config.get("colors", {}).get("warning", "#FFA500")}; }}
    .status-danger {{ background-color: {brand_config.get("colors", {}).get("danger", "red")}; }}
    
    /* Dashboard grid layout */
    .grid-container {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 16px;
        margin-bottom: 1rem;
    }}
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}

    .stTabs [data-baseweb="tab"] {{
        background-color: #f1f3f5;
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-weight: 500;
    }}

    .stTabs [aria-selected="true"] {{
        background-color: white !important;
        border-bottom: 3px solid {primary_color} !important;
    }}
    
    /* Progress bar */
    .progress-container {{
        width: 100%;
        background-color: #e9ecef;
        border-radius: 8px;
        margin-bottom: 0.5rem;
    }}
    
    .progress-bar {{
        height: 10px;
        border-radius: 8px;
    }}
    
    .progress-bar-ok {{ background-color: {brand_config.get("colors", {}).get("secondary", "green")}; }}
    .progress-bar-warning {{ background-color: {brand_config.get("colors", {}).get("warning", "#FFA500")}; }}
    .progress-bar-danger {{ background-color: {brand_config.get("colors", {}).get("danger", "red")}; }}
    
    /* Maintenance countdown */
    .countdown {{
        text-align: center;
        font-size: 1.5rem;
        font-weight: 600;
    }}
    
    /* Header styling */
    .app-header {{
        background-color: {primary_color};
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }}
    
    .app-header-content {{
        margin-left: 20px;
    }}
    
    .app-header img {{
        height: 60px;
    }}
    
    /* Other existing styles */
    .stButton>button {{
        background-color: {primary_color} !important;
        color: white !important;
        border: none !important;
        border-radius: 4px !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }}
    
    .stButton>button:hover {{
        background-color: {accent_color} !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1) !important;
    }}
    
    .metrics-container {{
        background-color: {brand_config.get("css_elements", {}).get("metrics_box_bg", "#F1F3F4")};
        border-radius: 5px;
        padding: 1.5rem;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }}
    
    .metrics-container .stMetric {{
        background-color: white;
        border-radius: 4px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }}
    
    .metrics-container [data-testid="stMetricValue"] {{
        color: {primary_color} !important;
        font-weight: bold !important;
        font-size: 1.8rem !important;
    }}
    
    .dataframe {{
        font-family: '{primary_font}', sans-serif !important;
    }}
    
    [data-testid="stTable"] th {{
        background-color: {brand_config.get("styling", {}).get("table_header_bg", "#006161")} !important;
        color: {brand_config.get("styling", {}).get("table_header_text", "#FFFFFF")} !important;
        font-weight: 500 !important;
    }}
    
    [data-testid="stTable"] tr:nth-of-type(even) {{
        background-color: {brand_config.get("styling", {}).get("table_stripe_color", "#F8F9FA")};
    }}
    
    .app-footer {{
        background-color: {brand_config.get("css_elements", {}).get("footer_bg", "#F1F3F4")};
        padding: 1rem;
        text-align: center;
        border-radius: 5px;
        margin-top: 2rem;
        font-size: 0.8rem;
        color: {dark_color};
    }}
    
    [data-testid="stSidebar"] {{
        background-color: {light_color} !important;
    }}
    
    .streamlit-expanderHeader {{
        background-color: {light_color};
        color: {dark_color} !important;
        font-family: '{primary_font}', sans-serif !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def apply_slot_filtering_rules(df):
    """
    Apply the rule: for stations with FEWER THAN 10 total slots, only consider slots 1-4
    Returns filtered dataframe
    """
    if 'slot' not in df.columns or df.empty:
        return df
    
    # Create a copy to avoid modifying the original
    filtered_df = df.copy()
    
    # Extract numeric values from slot names if they're strings (e.g., "Slot 1" -> 1)
    def extract_slot_number(slot_value):
        # First, check for NaN values
        import pandas as pd
        if pd.isna(slot_value):
            return None
            
        if isinstance(slot_value, str):
            # Extract digits from string
            import re
            digits = re.findall(r'\d+', slot_value)
            if digits:
                return int(digits[0])
        elif isinstance(slot_value, (int, float)):
            # Make sure it's not NaN before converting to int
            try:
                return int(slot_value)
            except (ValueError, OverflowError):
                return None
        return None
    
    # Create a temporary column with numeric slot values
    filtered_df['slot_num'] = filtered_df['slot'].apply(extract_slot_number)
    
    # Count unique slots per station
    slot_counts = filtered_df.groupby('stationName')['slot'].nunique()
    
    # Identify stations with fewer than 10 total slots
    stations_with_few_slots = slot_counts[slot_counts < 10].index.tolist()
    
    # Create mask to keep:
    # 1. All rows from stations NOT in stations_with_few_slots
    # 2. Only rows with slots 1-4 from stations IN stations_with_few_slots
    valid_slots_mask = filtered_df['slot_num'].isin([1, 2, 3, 4])
    
    mask = (~filtered_df['stationName'].isin(stations_with_few_slots)) | \
           (filtered_df['stationName'].isin(stations_with_few_slots) & valid_slots_mask)
    
    # Apply the mask and drop the temporary column
    result_df = filtered_df[mask].drop(columns=['slot_num'])
    
    return result_df

# Modified function to load shelf layout from database
def load_shelf_layout():
    """Load shelf layout configuration from database"""
    db_config = load_database_config()
    
    if not db_config:
        st.warning("Database configuration not found. Cannot load shelf layout.")
        return create_default_shelf_layout()
    
    conn = None
    cursor = None
    try:
        conn_params = db_config.get("connection", {})
        db_type = conn_params.get("type", "").lower()
        
        # Get connection based on database type
        if db_type == "mysql":
            conn = mysql.connector.connect(
                host=conn_params.get("host"),
                port=conn_params.get("port", 3306),
                user=conn_params.get("user"),
                password=conn_params.get("password"),
                database=conn_params.get("database")
            )
            
            # Check if table exists, create if it doesn't
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES LIKE 'shelf_layout'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Create the shelf_layout table
                st.info("Creating shelf layout table in database...")
                create_table_sql = """
                CREATE TABLE shelf_layout (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    shelf INT NOT NULL,
                    position INT NOT NULL,
                    station VARCHAR(255),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_shelf_position (shelf, position)
                )
                """
                cursor.execute(create_table_sql)
                conn.commit()
                # Return default empty layout
                return create_default_shelf_layout()
            
            # Table exists, query for data
            query = "SELECT shelf, position, station FROM shelf_layout ORDER BY shelf, position"
            cursor.execute(query)
            
            # Process results
            layout = {}
            for (shelf, position, station) in cursor:
                key = f"shelf_{shelf}_position_{position}"
                layout[key] = station
            
            # If layout is empty, create and save default
            if not layout:
                layout = create_default_shelf_layout()
                save_shelf_layout(layout)
            
            return layout
            
        else:
            # Fallback to default layout for non-MySQL databases
            st.warning(f"Shelf layout not supported for {db_type} database type")
            return create_default_shelf_layout()
    
    except Exception as e:
        st.error(f"Error loading shelf layout data: {e}")
        return create_default_shelf_layout()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Modified function to save shelf layout to database
def save_shelf_layout(layout):
    """Save shelf layout configuration to database"""
    db_config = load_database_config()
    
    if not db_config:
        st.warning("Database configuration not found. Cannot save shelf layout.")
        return False
    
    conn = None
    cursor = None
    try:
        conn_params = db_config.get("connection", {})
        db_type = conn_params.get("type", "").lower()
        
        if db_type == "mysql":
            conn = mysql.connector.connect(
                host=conn_params.get("host"),
                port=conn_params.get("port", 3306),
                user=conn_params.get("user"),
                password=conn_params.get("password"),
                database=conn_params.get("database")
            )
            
            cursor = conn.cursor()
            
            # First, check if table exists
            cursor.execute("SHOW TABLES LIKE 'shelf_layout'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Create the shelf_layout table
                create_table_sql = """
                CREATE TABLE shelf_layout (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    shelf INT NOT NULL,
                    position INT NOT NULL,
                    station VARCHAR(255),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_shelf_position (shelf, position)
                )
                """
                cursor.execute(create_table_sql)
                conn.commit()
            
            # Clear existing data
            cursor.execute("DELETE FROM shelf_layout")
            
            # Insert new data
            for key, station in layout.items():
                # Parse shelf and position from key
                parts = key.split('_')
                if len(parts) >= 4:
                    try:
                        shelf = int(parts[1])
                        position = int(parts[3])
                        
                        # Insert into database
                        query = """
                        INSERT INTO shelf_layout (shelf, position, station)
                        VALUES (%s, %s, %s)
                        """
                        cursor.execute(query, (shelf, position, station))
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing key {key}: {e}")
            
            # Commit all changes
            conn.commit()
            return True
            
        else:
            st.warning(f"Shelf layout saving not supported for {db_type} database type")
            return False
            
    except Exception as e:
        st.error(f"Error saving shelf layout data: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Leave the create_default_shelf_layout function unchanged as it only creates an in-memory layout
def create_default_shelf_layout():
    """Create a default empty shelf layout configuration"""
    layout = {}
    for shelf in range(1, 5):  # 4 shelves
        for position in range(1, 9):  # 8 positions each
            key = f"shelf_{shelf}_position_{position}"
            layout[key] = None
    return layout

def calculate_maintenance_due(df):
    """Calculate maintenance due dates if they don't exist"""
    # Make a copy to avoid warnings
    df = df.copy()
    
    # Check if we have lastMaintenance column but no maintenanceDue
    if 'lastMaintenance' in df.columns and 'maintenanceDue' not in df.columns:
        # Ensure lastMaintenance is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['lastMaintenance']):
            df['lastMaintenance'] = pd.to_datetime(df['lastMaintenance'], errors='coerce')
            
        # Calculate days since last maintenance
        df['daysSinceLastMaintenance'] = (datetime.now() - df['lastMaintenance']).dt.days
        
        # Assume maintenance is due every 30 days
        df['maintenanceDue'] = 30 - df['daysSinceLastMaintenance']
    elif 'maintenanceDue' not in df.columns:
        # If no maintenance data, just show a warning but don't add any dummy data
        st.warning("No maintenance data found. Some features will be limited.")
        # Leave the dataframe as is, without adding dummy values
    
    return df

def display_shelf_layout_map(df):
    """Display a visual representation of shelves with station assignments"""
    st.subheader("Shelf Layout Configuration")
    
    # Load current layout configuration
    if 'shelf_layout' not in st.session_state:
        st.session_state.shelf_layout = load_shelf_layout()
        
    # Initialize edit mode if not in session state (default to False)
    if 'edit_layout_mode' not in st.session_state:
        st.session_state.edit_layout_mode = False
    
    # Get unique station names from data
    available_stations = sorted([str(x) for x in df['stationName'].unique().tolist()])
    
    # Add option for "None" (no assignment)
    station_options = ["None"] + available_stations
    
    # Use custom CSS for the shelf layout
    st.markdown("""
    <style>
    .shelf-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        border: 2px solid #e9ecef;
    }
    .shelf-title {
        font-weight: 600;
        margin-bottom: 10px;
        color: #495057;
    }
    .position-box {
        background-color: white;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 10px;
        min-height: 80px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: all 0.2s;
    }
    .position-box:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .position-number {
        font-size: 0.8rem;
        color: #6c757d;
    }
    .station-assigned {
        font-weight: 500;
        color: #212529;
    }
    .station-readonly {
        padding: 8px 12px;
        background-color: #f9f9f9;
        border: 1px solid #ddd;
        border-radius: 4px;
        text-align: center;
        margin: 5px 0;
        font-weight: 500;
    }
    .edit-mode-indicator {
        background-color: #e7f3ff;
        color: #0d6efd;
        padding: 5px 10px;
        border-radius: 4px;
        display: inline-block;
        font-size: 0.8rem;
        margin-right: 10px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Edit/Save buttons
    save_col1, save_col2, save_col3 = st.columns([2, 1, 1])
    
    with save_col1:
        if st.session_state.edit_layout_mode:
            st.markdown('<div class="edit-mode-indicator">Edit Mode Active</div>', unsafe_allow_html=True)
    
    with save_col2:
        # Toggle edit mode button
        button_label = "Exit Edit Mode" if st.session_state.edit_layout_mode else "Edit Layout"
        if st.button(button_label):
            st.session_state.edit_layout_mode = not st.session_state.edit_layout_mode
            st.rerun()
    
    with save_col3:
        # Save button - only show in edit mode
        if st.session_state.edit_layout_mode:
            if st.button("Save Layout"):
                if save_shelf_layout(st.session_state.shelf_layout):
                    st.success("Shelf layout saved successfully!")
                else:
                    st.error("Error saving shelf layout")
    
    # Create shelves (4 shelves total)
    for shelf in range(1, 5):
        st.markdown(f"""
        <div class="shelf-container">
            <div class="shelf-title">Shelf {shelf}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Create 8 positions per shelf using columns
        cols = st.columns(8)
        
        for position in range(1, 9):
            with cols[position-1]:
                # Generate key for session state
                position_key = f"shelf_{shelf}_position_{position}"
                
                # Get currently assigned station (if any)
                current_station = st.session_state.shelf_layout.get(position_key)
                
                # Show position number
                st.markdown(f"<div class='position-number'>Position {position}</div>", unsafe_allow_html=True)
                
                # In edit mode: show dropdown selector
                if st.session_state.edit_layout_mode:
                    # Set default selection
                    default_ix = 0
                    if current_station in available_stations:
                        default_ix = station_options.index(current_station)
                    
                    # Dropdown to select station for this position
                    selected_station = st.selectbox(
                        f"",  # No label needed
                        options=station_options,
                        index=default_ix,
                        key=position_key
                    )
                    
                    # Update session state when selection changes
                    if selected_station == "None":
                        st.session_state.shelf_layout[position_key] = None
                    else:
                        st.session_state.shelf_layout[position_key] = selected_station
                
                # In read-only mode: show static text
                else:
                    # Display station name or empty placeholder
                    if current_station:
                        st.markdown(f'<div class="station-readonly">{current_station}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="station-readonly" style="color:#999">Empty</div>', unsafe_allow_html=True)
                
                # Display status indicators (always visible in both modes)
                if current_station and current_station != "None":
                    # Check if station has maintenance data
                    has_maintenance = False
                    maintenance_status = "Unknown"
                    status_color = "#6c757d"  # Default gray
                    
                    try:
                        if 'maintenanceDue' in df.columns:
                            station_data = df[df['stationName'] == current_station]
                            if not station_data.empty:
                                has_maintenance = True
                                min_due = station_data['maintenanceDue'].min()
                                if min_due < 0:
                                    maintenance_status = "Overdue"
                                    status_color = "#dc3545"  # Red
                                elif min_due <= 7:
                                    maintenance_status = "Due Soon"
                                    status_color = "#ffc107"  # Yellow
                                else:
                                    maintenance_status = "OK"
                                    status_color = "#28a745"  # Green
                    except Exception as e:
                        print(f"Error checking maintenance status: {e}")
                    
                    if has_maintenance:
                        st.markdown(f"""
                        <div style="margin-top:5px; color:{status_color};">
                            <span style="font-weight:bold;">●</span> {maintenance_status}
                        </div>
                        """, unsafe_allow_html=True)

def display_maintenance(df):
    """Display detailed maintenance information"""
    st.header("Maintenance Schedule")
    
    # Map maintenance_control table columns to expected columns if they don't exist
    maintenance_df = df.copy()
    
    # Debug output to check what columns are available
    print(f"Available columns: {maintenance_df.columns.tolist()}")
    
    # Check if maintenance data columns exist, try to map from actual table columns if not
    if 'lastMaintenance' not in maintenance_df.columns and 'maintenanceDate' in maintenance_df.columns:
        maintenance_df['lastMaintenance'] = maintenance_df['maintenanceDate']
        
    if 'maintenanceDue' not in maintenance_df.columns:
        # If scheduledDate exists, calculate days until due
        if 'scheduledDate' in maintenance_df.columns:
            # Calculate days between now and scheduled date - with proper type handling
            today = datetime.now()
            
            # Ensure proper datetime conversion and handle the calculation safely
            try:
                # First convert to datetime objects if not already
                if not pd.api.types.is_datetime64_any_dtype(maintenance_df['scheduledDate']):
                    maintenance_df['scheduledDate'] = pd.to_datetime(maintenance_df['scheduledDate'], errors='coerce')
                
                # Calculate days difference row by row to avoid array operations that might fail
                maintenance_df['maintenanceDue'] = maintenance_df['scheduledDate'].apply(
                    lambda x: (x - today).days if pd.notna(x) else 30
                )
            except Exception as e:
                st.warning(f"Error calculating maintenance due dates: {e}")
                # Fallback to a default value
                maintenance_df['maintenanceDue'] = 30
                
        elif 'lastMaintenance' in maintenance_df.columns or 'maintenanceDate' in maintenance_df.columns:
            # Fallback: calculate based on last maintenance (assuming 30-day maintenance cycle)
            reference_date_col = 'lastMaintenance' if 'lastMaintenance' in maintenance_df.columns else 'maintenanceDate'
            
            # Ensure reference date is properly converted to datetime
            if not pd.api.types.is_datetime64_any_dtype(maintenance_df[reference_date_col]):
                maintenance_df[reference_date_col] = pd.to_datetime(maintenance_df[reference_date_col], errors='coerce')
            
            # Calculate the days safely
            today = datetime.now()
            maintenance_df['maintenanceDue'] = maintenance_df[reference_date_col].apply(
                lambda x: 30 - (today - x).days if pd.notna(x) else 30
            )
    
    # Check if essential maintenance columns exist after mapping
    required_cols_for_display = ['lastMaintenance', 'maintenanceDue']
    missing_display_cols = [col for col in required_cols_for_display if col not in maintenance_df.columns]

    if missing_display_cols:
        st.error(f"Maintenance display requires the following columns which are missing from the loaded data: {', '.join(missing_display_cols)}")
        st.info("Please ensure the database includes maintenance information or update your column mapping.")
        st.warning("Maintenance features will be unavailable.")
        return # Exit the function early

    # Use database status column if available, otherwise calculate it
    if 'status' not in maintenance_df.columns:
        if 'maintenanceStatus' in maintenance_df.columns:
            maintenance_df['status'] = maintenance_df['maintenanceStatus']
        else:
            # Calculate status based on maintenanceDue
            maintenance_df['status'] = 'OK'
            maintenance_df.loc[maintenance_df['maintenanceDue'] <= 7, 'status'] = 'Due Soon'
            maintenance_df.loc[maintenance_df['maintenanceDue'] < 0, 'status'] = 'Overdue'
    
    # Get latest entry for each station-slot combination to prevent duplicates
    if 'testDate' in maintenance_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(maintenance_df['testDate']):
            maintenance_df['testDate'] = pd.to_datetime(maintenance_df['testDate'], errors='coerce')
        maintenance_df = maintenance_df.sort_values('testDate', ascending=False)
    elif 'timestamp' in maintenance_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(maintenance_df['timestamp']):
            maintenance_df['timestamp'] = pd.to_datetime(maintenance_df['timestamp'], errors='coerce')
        maintenance_df = maintenance_df.sort_values('timestamp', ascending=False)
    
    maintenance_df = maintenance_df.drop_duplicates(subset=['stationName', 'slot'])
    
    # Check for optional maintenance columns but don't exit if missing
    optional_columns = ['maintenanceStatus', 'scheduledMaintenance', 'maintenanceNotes']
    missing_columns = [col for col in optional_columns if col not in maintenance_df.columns]
    
    if missing_columns:
        st.info(f"Some optional maintenance data might not be available: {', '.join(missing_columns)}")
    else:
        st.success("All maintenance data features are available!")
    
    stations_slots = maintenance_df[['stationName', 'slot']]
    
    st.subheader("Station & Slot Maintenance Overview")
    
    with st.expander("View Maintenance Status by Station", expanded=True):
        manager_df = pd.DataFrame()
        manager_df['Station'] = stations_slots['stationName']
        manager_df['Slot'] = stations_slots['slot']
        
        merge_columns = ['stationName', 'slot']
        display_columns = []
        
        # Determine which columns we can use for the merge
        if 'lastMaintenance' in maintenance_df.columns:
            merge_columns.append('lastMaintenance')
            display_columns.append('lastMaintenance')
        elif 'maintenanceDate' in maintenance_df.columns:
            merge_columns.append('maintenanceDate')
            display_columns.append('maintenanceDate')
            
        merge_columns.append('maintenanceDue')
        display_columns.append('maintenanceDue')
        
        if 'status' in maintenance_df.columns:
            merge_columns.append('status')
            display_columns.append('status')
            
        if 'maintenanceNotes' in maintenance_df.columns:
            merge_columns.append('maintenanceNotes')
        
        manager_df = manager_df.merge(
            maintenance_df[merge_columns],
            left_on=['Station', 'Slot'],
            right_on=['stationName', 'slot'],
            how='left'
        )
        
        # Format the dates for display - safely handle non-datetime columns
        if 'lastMaintenance' in manager_df.columns:
            try:
                # First ensure it's really a datetime column
                if not pd.api.types.is_datetime64_any_dtype(manager_df['lastMaintenance']):
                    manager_df['lastMaintenance'] = pd.to_datetime(manager_df['lastMaintenance'], errors='coerce')
                # Now it's safe to use .dt
                manager_df['Last Maintenance'] = manager_df['lastMaintenance'].dt.strftime('%Y-%m-%d').fillna('N/A')
            except Exception as e:
                # If conversion fails, just use the original column with string formatting
                manager_df['Last Maintenance'] = manager_df['lastMaintenance'].astype(str).replace('NaT', 'N/A')
                st.warning(f"Error formatting maintenance dates: {e}")
        elif 'maintenanceDate' in manager_df.columns:
            try:
                # First ensure it's really a datetime column
                if not pd.api.types.is_datetime64_any_dtype(manager_df['maintenanceDate']):
                    manager_df['maintenanceDate'] = pd.to_datetime(manager_df['maintenanceDate'], errors='coerce')
                # Now it's safe to use .dt
                manager_df['Last Maintenance'] = manager_df['maintenanceDate'].dt.strftime('%Y-%m-%d').fillna('N/A')
            except Exception as e:
                # If conversion fails, just use the original column with string formatting
                manager_df['Last Maintenance'] = manager_df['maintenanceDate'].astype(str).replace('NaT', 'N/A')
                st.warning(f"Error formatting maintenance dates: {e}")
        else:
            manager_df['Last Maintenance'] = 'N/A'
            
        # Handle numeric columns safely
        try:
            manager_df['Days Until Due'] = manager_df['maintenanceDue'].fillna(0).astype(int)
        except Exception as e:
            manager_df['Days Until Due'] = 'Unknown'
            st.warning(f"Error formatting due days: {e}")
        
        if 'status' in manager_df.columns:
            manager_df['Status'] = manager_df['status'].fillna('Unknown')
        else:
            # Calculate status based on days until due
            manager_df['Status'] = 'OK'
            try:
                days_until_due = pd.to_numeric(manager_df['Days Until Due'], errors='coerce')
                manager_df.loc[days_until_due <= 7, 'Status'] = 'Due Soon'
                manager_df.loc[days_until_due < 0, 'Status'] = 'Overdue'
            except Exception as e:
                st.warning(f"Error calculating status: {e}")
        
        # Create a clean display dataframe
        display_df = manager_df[['Station', 'Slot', 'Last Maintenance', 'Days Until Due', 'Status']].copy()
        
        st.dataframe(display_df.reset_index(drop=True), use_container_width=True, hide_index=True)
    
    st.subheader("Maintenance Status by Station")
    
    try:
        # DEBUG: Print maintenance status distribution
        status_counts = maintenance_df['status'].value_counts().to_dict() if 'status' in maintenance_df.columns else {}
        st.write(f"Number of rows with status values: {status_counts}")
        
        # Create a basic table even if we don't have complete status data
        stations_df = maintenance_df[['stationName']].drop_duplicates()
        
        if not stations_df.empty:
            # Create a display dataframe for stations
            summary_df = pd.DataFrame()
            summary_df['Rig Name'] = stations_df['stationName']
            
            # Add status columns with defaults
            for status in ['Overdue', 'Due Soon', 'OK']:
                summary_df[status] = 0
                
            # If we have status data, use it to populate the summary
            if 'status' in maintenance_df.columns and not maintenance_df['status'].isna().all():
                # Group by station and status to count occurrences
                try:
                    status_counts = maintenance_df.groupby(['stationName', 'status']).size().reset_index(name='count')
                    
                    # Update the summary dataframe with actual counts
                    for _, row in status_counts.iterrows():
                        station = row['stationName']
                        status = row['status']
                        if status in ['Overdue', 'Due Soon', 'OK']:
                            mask = summary_df['Rig Name'] == station
                            summary_df.loc[mask, status] = row['count']
                except Exception as e:
                    st.warning(f"Could not summarize status counts: {e}")
            else:
                # If no status data is available, we'll still show the station list
                st.info("Status values are not available. Showing station list with empty status counts.")
                
            # Display the summary table
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            # Try to create a chart if there's at least some status data
            if 'status' in maintenance_df.columns and not maintenance_df['status'].isna().all():
                try:
                    # Prepare data for plotting
                    plot_data = []
                    for _, row in summary_df.iterrows():
                        station = row['Rig Name']
                        for status in ['Overdue', 'Due Soon', 'OK']:
                            count = row[status]
                            if count > 0:
                                plot_data.append({'Rig Name': station, 'status': status, 'count': count})
                    
                    if plot_data:
                        plot_df = pd.DataFrame(plot_data)
                        
                        fig = px.bar(
                            plot_df, 
                            x='Rig Name',
                            y='count',
                            color='status',
                            title='Maintenance Status by Station',
                            color_discrete_map={
                                'OK': '#28a745',
                                'Due Soon': '#ffc107',
                                'Overdue': '#dc3545'
                            },
                            labels={'Rig Name': 'Rig Name', 'count': 'Number of Slots', 'status': 'Status'}
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No status data available for charting.")
                except Exception as e:
                    st.warning(f"Could not create status chart: {e}")
        else:
            st.info("No station data available to display.")
            
    except Exception as e:
        st.error(f"Error displaying maintenance status: {e}")
    
    # Continue with filter section
    st.subheader("Filter Maintenance Items")
    
    col1, col2 = st.columns(2)
    
    with col1:
        status_options = ['Overdue', 'Due Soon', 'OK']
        selected_status = st.multiselect(
            "Filter by Status", 
            options=status_options,
            default=['Overdue', 'Due Soon']
        )
    
    with col2:
        sort_by = st.selectbox(
            "Sort by",
            options=["Due Date (ascending)", "Due Date (descending)", "Station Name"]
        )
    
    if selected_status:
        filtered_df = maintenance_df[maintenance_df['status'].isin(selected_status)]
    else:
        filtered_df = maintenance_df
    
    if sort_by == "Due Date (ascending)":
        filtered_df = filtered_df.sort_values(by='maintenanceDue')
    elif sort_by == "Due Date (descending)":
        filtered_df = filtered_df.sort_values(by='maintenanceDue', ascending=False)
    else:
        filtered_df = filtered_df.sort_values(by=['stationName', 'slot'])
    
    if not filtered_df.empty:
        st.subheader(f"Maintenance Items ({len(filtered_df)} items)")
        
        for _, row in filtered_df.iterrows():
            status_color = {
                'Overdue': '#dc3545',
                'Due Soon': '#ffc107',
                'OK': '#28a745'
            }.get(row.get('status', 'Unknown'), '#6c757d')
            
            # Format the date display safely
            last_maint_display = "Unknown"
            if 'lastMaintenance' in row and pd.notna(row['lastMaintenance']):
                try:
                    last_maint_display = row['lastMaintenance'].strftime('%Y-%m-%d')
                except:
                    pass
            elif 'maintenanceDate' in row and pd.notna(row['maintenanceDate']):
                try:
                    last_maint_display = row['maintenanceDate'].strftime('%Y-%m-%d')
                except:
                    pass
                    
            # Format days until due safely
            days_due_display = "Unknown"
            if 'maintenanceDue' in row and pd.notna(row['maintenanceDue']):
                try:
                    days_due_display = int(row['maintenanceDue'])
                except:
                    pass
                    
            # Format scheduled date if available
            scheduled_display = "Not scheduled"
            if 'scheduledDate' in row and pd.notna(row['scheduledDate']):
                try:
                    scheduled_display = row['scheduledDate'].strftime('%Y-%m-%d')
                except:
                    pass
                    
            # Format notes if available
            notes_display = ""
            if 'maintenanceNotes' in row and pd.notna(row['maintenanceNotes']):
                notes_display = f"""
                <div style="margin-top: 8px; padding: 8px; background-color: #f8f9fa; border-radius: 4px;">
                    <strong>Notes:</strong> {row['maintenanceNotes']}
                </div>
                """
            
            st.markdown(f"""
            <div style="background-color: white; border-left: 5px solid {status_color}; 
                 border-radius: 5px; padding: 15px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0;">{row['stationName']} - {row['slot']}</h3>
                    <span style="background-color: {status_color}; color: white; padding: 5px 10px; border-radius: 20px;">
                        {row.get('status', 'Unknown')}
                    </span>
                </div>
                <div style="margin-top: 10px;">
                    <p><strong>Last Maintenance:</strong> {last_maint_display}</p>
                    <p><strong>Days Until Due:</strong> {days_due_display}</p>
                    <p><strong>Scheduled Date:</strong> {scheduled_display}</p>
                    {notes_display}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No maintenance items match your filters")

def display_test_results(df):
    """Display test results data"""
    st.header("Test Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        station_options = ["All Stations"] + sorted([str(x) for x in df['stationName'].unique().tolist()])
        selected_station = st.selectbox("Filter by Station:", station_options)
    
    with col2:
        result_options = ["All Results"] + sorted([str(x) for x in df['result'].unique().tolist()])
        selected_result = st.selectbox("Filter by Result:", result_options)
    
    filtered_df = df.copy()
    if selected_station != "All Stations":
        filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
    if selected_result != "All Results":
        filtered_df = filtered_df[filtered_df['result'] == selected_result]
    
    if not filtered_df.empty:
        st.subheader("Results Summary")
        
        total = len(filtered_df)
        passed = filtered_df[filtered_df['result'].str.contains('PASSED', case=False, na=False)].shape[0]
        failed = total - passed
        pass_rate = round((passed / total) * 100) if total > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Tests", total)
        with col2:
            st.metric("Passed", passed)
        with col3:
            st.metric("Pass Rate", f"{pass_rate}%")
        
        st.subheader("Test Results Data")
        st.dataframe(filtered_df.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.info("No data matches your filters")

def main():
    from database_helpers import initialize_database
    success, message = initialize_database()
    if not success:
        st.error(f"Database initialization failed: {message}")
    
    if brand_config:
        company_name = brand_config.get("company_information", {}).get("company_name", "Test Station Maintenance Control")
        
        logo_path = None
        possible_logo_paths = [
            Path(get_app_dir()) / brand_config.get("assets", {}).get("logo_path", ""),
            Path("assets") / "logo.png",
            Path("./assets/logo.png")
        ]
        
        for path in possible_logo_paths:
            if path.exists():
                logo_path = path
                break
        
        header_html = f"""
        <style>
        .header-company-name {{
            color: white !important;
            font-weight: 600 !important;
            margin: 0 !important;
            text-shadow: none !important;
            font-family: '{primary_font}', sans-serif !important;
        }}
        .header-subtitle {{
            color: white !important;
            margin: 0 !important;
            text-shadow: none !important;
            font-family: '{primary_font}', sans-serif !important;
        }}
        </style>
        <div class="app-header">
        """
        
        if logo_path and logo_path.exists():
            header_html += f'<img src="data:image/png;base64,{get_image_as_base64(logo_path)}" alt="{company_name} Logo">'
            
        header_html += f"""
            <div class="app-header-content">
                <h2 class="header-company-name">{company_name}</h2>
                <p class="header-subtitle">Test Station Maintenance Control</p>
            </div>
        </div>
        """
        st.markdown(header_html, unsafe_allow_html=True)
    else:
        st.title("Test Station Maintenance Control")
    
    st.markdown("Track and monitor the status of your test stations")
    
    with st.sidebar:
        st.header("Controls")
        
        refresh = st.button("Refresh Database")
        
        st.subheader("Date Filter")
        
        today = datetime.now().date()
        last_month = today - timedelta(days=30)
        
        start_date = st.date_input(
            "Start Date",
            value=last_month,
            max_value=today
        )
        
        end_date = st.date_input(
            "End Date",
            value=today,
            min_value=start_date,
            max_value=today
        )
        
        disable_date_filter = st.checkbox("Show all dates", value=False)
            
        st.markdown("---")
        st.markdown("### About")
        st.markdown(
            "This app provides visualization and analysis of test station maintenance status."
        )
    
    df = None
    error_message = None
    
    df, error_message = load_data_from_database()
    if df is not None:
        st.success(f"Loaded {len(df)} records from database")
    
    try:
        filter_rules = {}
        possible_rules_paths = [
            Path(get_app_dir()) / "filter_rules.json",
            Path("filter_rules.json"),
            Path("./filter_rules.json")
        ]
        
        for path in possible_rules_paths:
            if path.exists():
                with open(path, "r") as f:
                    filter_rules = json.load(f)
                break
                
        for rule in filter_rules.get("filters", []):
            if rule.get("column") == "result" and rule.get("condition") == "contains":
                pattern = rule.get("value", "")
                if pattern:
                    df = df[~df["result"].str.contains(pattern, case=False, na=False)]
            elif rule.get("column") == "slot" and rule.get("condition") == "greater_than":
                try:
                    threshold = float(rule.get("value", "0"))
                    df = df[df["slot"].str.extract(r'(\d+)', expand=False).fillna("0").astype(float) <= threshold]
                except Exception as e:
                    st.warning("Error applying slot filter rule: " + str(e))
            elif (rule.get("column") == "result" and 
                  rule.get("condition") == "equals" and 
                  rule.get("action") == "replace"):
                old_val = rule.get("value", "")
                new_val = rule.get("new_value", "")
                if old_val and new_val:
                    df["result"] = df["result"].replace(old_val, new_val)
    except Exception as e:
        st.warning("Could not apply filter rules: " + str(e))
    
    if error_message:
        st.error(error_message)
        
        st.info("Please check your database connection settings in config/database_config.json")
        
        conn_details = load_database_config().get("connection", {})
        if "password" in conn_details:
            conn_details["password"] = "****"
        
        st.code(json.dumps(conn_details, indent=2), language="json")
    
    if df is not None:
        if 'testDate' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['testDate']):
            df = parse_date_column(df, 'testDate')
            
        if 'lastMaintenance' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['lastMaintenance']):
            df = parse_date_column(df, 'lastMaintenance')
            
        df = calculate_maintenance_due(df)
        
        df = apply_slot_filtering_rules(df)
        
        if not disable_date_filter and 'testDate' in df.columns:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            date_filtered_df = df[(df['testDate'] >= start_datetime) & (df['testDate'] <= end_datetime)]
            
            if len(date_filtered_df) < len(df):
                st.info(f"Showing {len(date_filtered_df)} of {len(df)} records based on date filter ({start_date} to {end_date})")
                
            df = date_filtered_df
        
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔧 Maintenance", "📝 Test Results"])
        
        with tab1:
            display_dashboard(df)
            
        with tab2:
            display_maintenance(df)
            
        with tab3:
            display_test_results(df)
            
        if brand_config:
            company_name = brand_config.get("company_information", {}).get("company_name", "")
            footer_html = f"""
            <div class="app-footer">
                <p>© {datetime.now().year} {company_name}. All Rights Reserved.</p>
            </div>
            """
            st.markdown(footer_html, unsafe_allow_html=True)

def calculate_slot_pass_rate(df):
    """Calculate the pass rate for each station and slot combination"""
    grouped = df.groupby(['stationName', 'slot']).apply(
        lambda x: pd.Series({
            'total_tests': len(x),
            'passed_tests': sum(x['result'].str.contains('PASSED', case=False, na=False)),
            'pass_rate': round((sum(x['result'].str.contains('PASSED', case=False, na=False)) / len(x)) * 100) if len(x) > 0 else 0
        }),
        include_groups=False
    ).reset_index()
    
    grouped['rise_change_needed'] = grouped['pass_rate'] < 75
    
    return grouped.reset_index(drop=True)

def display_dashboard(df):
    """Display the main dashboard with key metrics and status"""
    st.header("Maintenance Dashboard")
    
    try:
        metrics = create_summary_metrics(df)
        if len(metrics) > 4:
            total, passed, failed, pass_rate, overdue, due_soon, ok_status = metrics
        else:
            total, passed, failed, pass_rate = metrics
            overdue, due_soon, ok_status = 0, 0, 0
            
        st.markdown('<div class="grid-container">', unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="card">
            <div class="card-header">Overall Status</div>
            <div style="text-align: center;">
                <div class="countdown" style="font-size: 2.5rem; margin-bottom: 1rem;">
                    {overdue + due_soon}
                </div>
                <div>
                    Stations Needing Maintenance
                </div>
                <div style="margin-top: 1rem;">
                    <span class="status-badge status-danger">{overdue} Overdue</span>
                    <span class="status-badge status-warning" style="margin-left: 8px;">{due_soon} Due Soon</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="card">
            <div class="card-header">Test Results</div>
            <div>
                <div class="progress-container">
                    <div class="progress-bar progress-bar-ok" style="width: {pass_rate}%;"></div>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <div><strong>Pass Rate:</strong> {pass_rate}%</div>
                    <div><strong>Total Tests:</strong> {total}</div>
                </div>
                <hr style="margin: 1rem 0;">
                <div style="display: flex; justify-content: space-between;">
                    <div>✅ Passed: {passed}</div>
                    <div>❌ Failed: {failed}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        stations = df['stationName'].nunique()
        slots = df['slot'].nunique()
        
        pass_rates = calculate_slot_pass_rate(df)
        low_pass_stations = pass_rates[pass_rates['pass_rate'] < 75]['stationName'].nunique()
        
        st.markdown(f"""
        <div class="card">
            <div class="card-header">Equipment Overview</div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">{stations}</div>
                <div>Test Stations</div>
                <hr style="margin: 1rem 0;">
                <div style="font-size: 1.2rem; color: #dc3545;">{low_pass_stations}</div>
                <div>Stations with Low Pass Rate Slots</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="card">
            <div class="card-header">Shelf Layout Map</div>
            <div>
                <p>Assign stations to shelf positions for visual tracking</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        display_shelf_layout_map(df)
        
        st.subheader("Status Overview")
        
        col1, col2 = st.columns(2)
        
        with col1:
            station_options = ["All Stations"] + sorted([str(x) for x in df['stationName'].unique().tolist()])
            selected_station = st.selectbox("Station:", station_options)
        
        with col2:
            filtered_df = df.copy()
            if selected_station != "All Stations":
                filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
            
            available_results = sorted([str(x) for x in filtered_df['result'].unique().tolist()])
            result_options = ["All Results"] + available_results
            selected_result = st.selectbox("Result:", result_options)
        
        if selected_station != "All Stations":
            filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
        if selected_result != "All Results":
            filtered_df = filtered_df[filtered_df['result'] == selected_result]
            
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="card"><div class="card-header">Test Results by Station</div>', unsafe_allow_html=True)
            if len(filtered_df) > 0:
                station_chart = create_station_chart(filtered_df)
                st.plotly_chart(station_chart, use_container_width=True)
            else:
                st.info("No data available with current filters")
            st.markdown('</div>', unsafe_allow_html=True)
                
        with col2:
            st.markdown('<div class="card"><div class="card-header">Maintenance Status</div>', unsafe_allow_html=True)
            if len(filtered_df) > 0 and 'maintenanceDue' in filtered_df.columns:
                maintenance_chart = create_maintenance_chart(filtered_df)
                st.plotly_chart(maintenance_chart, use_container_width=True)
            else:
                st.info("No maintenance data available")
            st.markdown('</div>', unsafe_allow_html=True)
        
        rise_changes_needed = sum(pass_rates['rise_change_needed'])
        
    except Exception as e:
        st.error(f"Error displaying dashboard: {e}")

if __name__ == "__main__":
    main()



