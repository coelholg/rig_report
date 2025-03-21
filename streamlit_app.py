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

# Set page configuration
st.set_page_config(
    page_title="Test Station Maintenance Control",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    return pd.DataFrame(data)

def get_app_dir():
    """Get the application directory in a way that works locally and on Streamlit Cloud"""
    try:
        # When running locally
        return Path(os.path.dirname(__file__))
    except:
        # When running on Streamlit Cloud
        return Path.cwd()

def try_load_default_csv():
    """Try to load the default CSV file if it exists"""
    try:
        # Try to find the file in multiple possible locations
        possible_paths = [
            Path(get_app_dir()) / 'results' / 'combined_results.csv',
            Path('results/combined_results.csv'),
            Path('./results/combined_results.csv')
        ]
        
        for path in possible_paths:
            if path.exists():
                df = pd.read_csv(path)
                # Extract required columns (assuming same structure as the HTML file)
                if len(df.columns) >= 9:
                    result_df = pd.DataFrame({
                        'stationName': df.iloc[:, 5],
                        'result': df.iloc[:, 6],
                        'slot': df.iloc[:, 7],
                        'testDate': df.iloc[:, 8]
                    })
                    return result_df, None
        
        return None, "Default CSV file not found"
    except Exception as e:
        return None, f"Error reading default CSV: {str(e)}"

def parse_uploaded_csv(uploaded_file):
    """Parse an uploaded CSV file"""
    try:
        df = pd.read_csv(uploaded_file)
        # Extract required columns (assuming same structure as the HTML file)
        if len(df.columns) >= 9:
            result_df = pd.DataFrame({
                'stationName': df.iloc[:, 5],
                'result': df.iloc[:, 6],
                'slot': df.iloc[:, 7],
                'testDate': df.iloc[:, 8]
            })
            return result_df, None
        else:
            return None, "CSV file doesn't have enough columns"
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
        })
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

# Main app function
def main():
    # Custom header with logo if available
    if brand_config:
        company_name = brand_config.get("company_information", {}).get("company_name", "Test Station Maintenance Control")
        
        # Try to find the logo in multiple possible locations
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
        <div class="app-header">
        """
        
        if logo_path and logo_path.exists():
            header_html += f'<img src="data:image/png;base64,{get_image_as_base64(logo_path)}" alt="{company_name} Logo">'
            
        header_html += f"""
            <div class="app-header-content">
                <h2 style="margin:0;" color="white" !important>{company_name}</h2>
                <p style="margin:0;">Test Station Maintenance Control</p>
            </div>
        </div>
        """
        st.markdown(header_html, unsafe_allow_html=True)
    else:
        # Fallback to standard title
        st.title("Test Station Maintenance Control")
    
    st.markdown("Track and monitor the status of your test stations")
    
    # Sidebar with modern layout
    with st.sidebar:
        st.header("Controls")
        
        # Data loading section
        st.subheader("Data Source")
        uploaded_file = st.file_uploader("Upload CSV File", type="csv")
        col1, col2 = st.columns(2)
        with col1:
            use_sample = st.button("Sample Data")
        with col2:
            refresh = st.button("Refresh")
            
        st.markdown("---")
        st.markdown("### About")
        st.markdown(
            "This app provides visualization and analysis of test station maintenance status."
        )
    
    # Data loading logic
    df = None
    error_message = None
    
    if uploaded_file is not None:
        df, error_message = parse_uploaded_csv(uploaded_file)
        if df is not None:
            st.success(f"Loaded data from uploaded file with {len(df)} records")
    elif use_sample:
        df = load_sample_data()
        st.info("Loaded sample data")
    else:
        # Try to load default CSV
        df, error_message = try_load_default_csv()
        if df is not None:
            st.success(f"Loaded data from default CSV with {len(df)} records")
    
    # Apply JSON filter rules before user filters
    try:
        # Try to load filter rules from multiple possible locations
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
                    # Drop rows where the "result" column contains the pattern
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
    
    # Display error if any
    if error_message:
        st.error(error_message)
        
        # If no data loaded yet, offer sample data
        if df is None:
            if st.button("Use Sample Data Instead"):
                df = load_sample_data()
                st.info("Loaded sample data")
    
    # Main content - only show if we have data
    if df is not None:
        # Add tabs for better navigation
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔧 Maintenance", "📝 Test Results"])
        
        with tab1:
            display_dashboard(df)
            
        with tab2:
            display_maintenance(df)
            
        with tab3:
            display_test_results(df)
            
        # Add footer with company info
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
    # Group by station and slot
    grouped = df.groupby(['stationName', 'slot']).apply(
        lambda x: pd.Series({
            'total_tests': len(x),
            'passed_tests': sum(x['result'].str.contains('PASSED', case=False, na=False)),
            'pass_rate': round((sum(x['result'].str.contains('PASSED', case=False, na=False)) / len(x)) * 100) if len(x) > 0 else 0
        })
    ).reset_index()
    
    # Add status for rise slot change needed
    grouped['rise_change_needed'] = grouped['pass_rate'] < 80
    
    return grouped

def display_dashboard(df):
    """Display the main dashboard with key metrics and status"""
    st.header("Maintenance Dashboard")
    
    try:
        # Get metrics including maintenance if available
        metrics = create_summary_metrics(df)
        if len(metrics) > 4:  # Has maintenance data
            total, passed, failed, pass_rate, overdue, due_soon, ok_status = metrics
        else:
            total, passed, failed, pass_rate = metrics
            overdue, due_soon, ok_status = 0, 0, 0
            
        # Display metrics in a grid
        st.markdown('<div class="grid-container">', unsafe_allow_html=True)
        
        # Card 1: Overall Status
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
        
        # Card 2: Test Results
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
        
        # Card 3: Stations Overview
        stations = df['stationName'].nunique()
        slots = df['slot'].nunique()
        st.markdown(f"""
        <div class="card">
            <div class="card-header">Equipment Overview</div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem;">{stations}</div>
                <div>Test Stations</div>
                <hr style="margin: 1rem 0;">
                <div style="font-size: 1.5rem;">{slots}</div>
                <div>Total Slots</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Close the grid container
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Charts section
        st.subheader("Status Overview")
        
        # Filter controls - updated to remove slot filter
        col1, col2 = st.columns(2)
        
        # Station filter only
        with col1:
            station_options = ["All Stations"] + sorted([str(x) for x in df['stationName'].unique().tolist()])
            selected_station = st.selectbox("Station:", station_options)
        
        # Result filter
        with col2:
            # Get available results based on station selection
            filtered_df = df.copy()
            if selected_station != "All Stations":
                filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
            
            available_results = sorted([str(x) for x in filtered_df['result'].unique().tolist()])
            result_options = ["All Results"] + available_results
            selected_result = st.selectbox("Result:", result_options)
        
        # Apply filters
        if selected_station != "All Stations":
            filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
        if selected_result != "All Results":
            filtered_df = filtered_df[filtered_df['result'] == selected_result]
            
        # Show charts in cards
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.subheader("Test Results by Station")
            if len(filtered_df) > 0:
                station_chart = create_station_chart(filtered_df)
                st.plotly_chart(station_chart, use_container_width=True)
            else:
                st.info("No data available with current filters")
            st.markdown('</div>', unsafe_allow_html=True)
                
        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.subheader("Maintenance Status")
            if len(filtered_df) > 0 and 'maintenanceDue' in filtered_df.columns:
                maintenance_chart = create_maintenance_chart(filtered_df)
                st.plotly_chart(maintenance_chart, use_container_width=True)
            else:
                st.info("No maintenance data available")
            st.markdown('</div>', unsafe_allow_html=True)
        
        pass_rates = calculate_slot_pass_rate(df)
        rise_changes_needed = sum(pass_rates['rise_change_needed'])
        
        if rise_changes_needed > 0:
            st.markdown(f"""
            <div class="card" style="border-left: 5px solid #dc3545; margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center;">
                    <div style="font-size: 2rem; margin-right: 1rem;">⚠️</div>
                    <div>
                        <h3 style="margin: 0;">Rise Component Alert</h3>
                        <p style="margin: 0.5rem 0 0 0;">
                            {rise_changes_needed} slot(s) have pass rates below 80% and need Rise component replacement.
                            <a href="#" onclick="document.querySelector('[data-testid=\\'stTabs\\'] [data-baseweb=\\'tab\\']').click(); 
                            return false;" style="color: #0366d6; text-decoration: none;">View Maintenance Tab</a>
                        </p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    except Exception as e:
        st.error(f"Error displaying dashboard: {e}")

def display_maintenance(df):
    """Display detailed maintenance information"""
    st.header("Maintenance Schedule")
    
    if 'maintenanceDue' not in df.columns:
        st.warning("Maintenance data not available in the current dataset")
        return
    
    # Create maintenance status categories
    maintenance_df = df.copy()
    maintenance_df['status'] = 'OK'
    maintenance_df.loc[maintenance_df['maintenanceDue'] <= 7, 'status'] = 'Due Soon'
    maintenance_df.loc[maintenance_df['maintenanceDue'] < 0, 'status'] = 'Overdue'
    
    # Calculate pass rates for each slot to determine Rise component changes
    pass_rates = calculate_slot_pass_rate(df)
    
    # Add information about slots needing rise component change
    st.markdown("""
    <div class="card">
        <div class="card-header">Rise Component Changes Needed</div>
        <div>Slots with pass rate below 80% need Rise component replacement.</div>
        <table style="width:100%; margin-top:1rem;">
            <tr style="background-color:#f1f3f5; font-weight:600;">
                <th style="padding:8px; text-align:left;">Station</th>
                <th style="padding:8px; text-align:left;">Slot</th>
                <th style="padding:8px; text-align:right;">Pass Rate</th>
                <th style="padding:8px; text-align:center;">Status</th>
            </tr>
    """, unsafe_allow_html=True)
    
    # Display slots needing rise component change
    for _, row in pass_rates.iterrows():
        status_color = "#28a745" if row['pass_rate'] >= 80 else "#dc3545"
        status_text = "OK" if row['pass_rate'] >= 80 else "Change Needed"
        
        st.markdown(f"""
            <tr>
                <td style="padding:8px;">{row['stationName']}</td>
                <td style="padding:8px;">{row['slot']}</td>
                <td style="padding:8px; text-align:right;">{row['pass_rate']}%</td>
                <td style="padding:8px; text-align:center;">
                    <span style="color:white; background-color:{status_color}; padding:4px 8px; border-radius:4px; font-size:0.8rem;">
                        {status_text}
                    </span>
                </td>
            </tr>
        """, unsafe_allow_html=True)
    
    st.markdown("</table></div>", unsafe_allow_html=True)
    
    # Filter options with dynamic slot options
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.multiselect(
            "Maintenance Status:",
            options=['Overdue', 'Due Soon', 'OK'],
            default=['Overdue', 'Due Soon']
        )
    
    with col2:
        sort_by = st.radio(
            "Sort by:",
            options=["Due Date", "Station Name", "Cycle Count"],
            horizontal=True
        )
        
    with col3:
        # Add filter for rise component change
        show_rise_change = st.checkbox("Show only slots needing Rise component change", False)
    
    # Apply filters
    if status_filter:
        maintenance_df = maintenance_df[maintenance_df['status'].isin(status_filter)]
    
    # Apply sorting
    if sort_by == "Due Date":
        maintenance_df = maintenance_df.sort_values(by='maintenanceDue')
    elif sort_by == "Station Name":
        maintenance_df = maintenance_df.sort_values(by=['stationName', 'slot'])
    else:  # Cycle Count
        if 'cycleCount' in maintenance_df.columns:
            maintenance_df = maintenance_df.sort_values(by='cycleCount', ascending=False)
    
    # Apply rise component filter if needed
    if show_rise_change:
        # Get list of station-slot pairs that need rise change
        need_rise_change = pass_rates[pass_rates['rise_change_needed']]
        if not need_rise_change.empty:
            # Create composite key for filtering
            need_rise_change['comp_key'] = need_rise_change['stationName'] + '-' + need_rise_change['slot'].astype(str)
            maintenance_df['comp_key'] = maintenance_df['stationName'] + '-' + maintenance_df['slot'].astype(str)
            maintenance_df = maintenance_df[maintenance_df['comp_key'].isin(need_rise_change['comp_key'])]
    
    # Display each maintenance item in a card
    st.subheader(f"Maintenance Items ({len(maintenance_df)})")
    
    for idx, row in maintenance_df.iterrows():
        # Check if this slot needs rise component change
        station_slot_key = f"{row['stationName']}-{row['slot']}"
        needs_rise = any((pass_rates['stationName'] + '-' + pass_rates['slot'].astype(str) == station_slot_key) & 
                          pass_rates['rise_change_needed'])
        
        status_class = "status-ok"
        if row['status'] == 'Overdue':
            status_class = "status-danger"
        elif row['status'] == 'Due Soon':
            status_class = "status-warning"
            
        # Add rise component badge if needed
        rise_badge = ""
        if needs_rise:
            rise_badge = """<span class="status-badge status-danger" style="margin-left: 8px;">Rise Change Needed</span>"""
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid {{'Overdue': '#dc3545', 'Due Soon': '#ffc107', 'OK': '#28a745'}}['{row['status']}'];">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0;">{row['stationName']} - {row['slot']}</h3>
                <div>
                    <span class="status-badge {status_class}">{row['status']}</span>
                    {rise_badge}
                </div>
            </div>
            <div style="margin-top: 1rem; display: flex; justify-content: space-between;">
                <div>
                    <p><strong>Last Maintenance:</strong> {row['lastMaintenance']}</p>
                    <p><strong>Due In:</strong> {row['maintenanceDue']} days</p>
                </div>
                <div>
                    <p><strong>Test Result:</strong> {row['result']}</p>
                    <p><strong>Test Date:</strong> {row['testDate']}</p>
                </div>
                <div>
                    <p><strong>Cycle Count:</strong> {row.get('cycleCount', 'N/A')}</p>
                    <button style="background-color: {primary_color}; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">Schedule Maintenance</button>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

def display_test_results(df):
    """Display test results data"""
    st.header("Test Results")
    
    # Filter options - updated to remove slot filter
    col1, col2 = st.columns(2)
    
    # Station filter
    with col1:
        station_options = ["All Stations"] + sorted([str(x) for x in df['stationName'].unique().tolist()])
        selected_station = st.selectbox("Filter by Station:", station_options)
    
    # Apply station filter for result options
    filtered_df = df.copy()
    if selected_station != "All Stations":
        filtered_df = filtered_df[filtered_df['stationName'].astype(str) == selected_station]
    
    # Result filter
    with col2:
        available_results = sorted([str(x) for x in filtered_df['result'].unique().tolist()])
        result_options = ["All Results"] + available_results
        selected_result = st.selectbox("Filter by Result:", result_options)
    
    # Apply result filter
    if selected_result != "All Results":
        filtered_df = filtered_df[filtered_df['result'].astype(str) == selected_result]
    
    # Display results in a modern table card
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    if not filtered_df.empty:
        # Group by slot to show summary by slot
        st.subheader(f"Slots for {selected_station if selected_station != 'All Stations' else 'All Stations'}")
        
        # Create a summary of slots for the station
        slot_summary = filtered_df.groupby('slot').apply(
            lambda x: pd.Series({
                'total_tests': len(x),
                'passed': sum(x['result'].str.contains('PASSED', case=False, na=False)),
                'failed': len(x) - sum(x['result'].str.contains('PASSED', case=False, na=False)),
                'pass_rate': round((sum(x['result'].str.contains('PASSED', case=False, na=False)) / len(x)) * 100) if len(x) > 0 else 0
            })
        ).reset_index()
        
        # Display a summary table of all slots
        st.dataframe(slot_summary, use_container_width=True)
        
        st.subheader("All Test Results")
        # Style the dataframe
        def highlight_results(row):
            if 'PASSED' in str(row['result']):
                return ['', f'background-color: {brand_config.get("colors", {}).get("secondary", "green")}30', '', '']
            else:
                return ['', f'background-color: {brand_config.get("colors", {}).get("danger", "red")}30', '', '']
                
        styled_df = filtered_df.style.apply(highlight_results, axis=1)
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.warning("No data available with current filters")
    
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
