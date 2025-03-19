import streamlit as st
import pandas as pd
import os
import plotly.express as px
from datetime import datetime
import matplotlib.pyplot as plt
import base64

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
        'testDate': ["2023-08-01", "2023-08-02", "2023-08-03", "2023-08-04", "2023-08-05"]
    }
    return pd.DataFrame(data)

def try_load_default_csv():
    """Try to load the default CSV file if it exists"""
    default_path = os.path.join(os.path.dirname(__file__), 'results', 'combined_results.csv')
    if os.path.exists(default_path):
        try:
            df = pd.read_csv(default_path)
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
            return None, f"Error reading default CSV: {str(e)}"
    return None, "Default CSV file not found"

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

def load_brand_config():
    import json
    config_path = os.path.join(os.path.dirname(__file__), "assets", "brand_config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        st.warning(f"Could not load brand config: {e}")
        return {}

def get_image_as_base64(image_path):
    """Convert an image to base64 for embedding in HTML/CSS"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        st.warning(f"Error loading image {image_path}: {e}")
        return ""

# Load brand configuration
brand_config = load_brand_config()

# Create comprehensive CSS based on brand config
if brand_config:
    # Try to load the logo for header
    logo_path = os.path.join(os.path.dirname(__file__), brand_config.get("assets", {}).get("logo_path", ""))
    logo_base64 = get_image_as_base64(logo_path) if os.path.exists(logo_path) else ""
    
    primary_color = brand_config.get("colors", {}).get("primary", "#000")
    secondary_color = brand_config.get("colors", {}).get("secondary", "#000")
    accent_color = brand_config.get("colors", {}).get("accent", "#000")
    danger_color = brand_config.get("colors", {}).get("danger", "#000")
    neutral_color = brand_config.get("colors", {}).get("neutral", "#000")
    light_color = brand_config.get("colors", {}).get("light", "#000")
    dark_color = brand_config.get("colors", {}).get("dark", "#000")
    
    primary_font = brand_config.get("fonts", {}).get("primary_font", "sans-serif")
    
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family={primary_font.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
    
    /* Base elements */
    body, .stApp {{
        font-family: '{primary_font}', sans-serif !important;
        color: {brand_config.get("css_elements", {}).get("body_color", "#000")};
    }}
    
    h1, h2, h3, h4, h5, h6 {{
        color: {brand_config.get("css_elements", {}).get("heading_color", "#000")} !important;
        font-family: '{primary_font}', sans-serif !important;
        font-weight: 600;
    }}
    
    /* Header styling */
    .app-header {{
        background-color: {brand_config.get("styling", {}).get("header_bg_color", "#000")};
        color: {brand_config.get("styling", {}).get("header_text_color", "#FFF")};
        padding: 1.5rem;
        border-radius: 5px;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
    }}
    
    .app-header-content {{
        margin-left: 20px;
    }}
    
    .app-header img {{
        height: 60px;
    }}
    
    /* Button styling */
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
    
    /* Metrics styling */
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
    
    /* Table styling */
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
    
    /* Footer styling */
    .app-footer {{
        background-color: {brand_config.get("css_elements", {}).get("footer_bg", "#F1F3F4")};
        padding: 1rem;
        text-align: center;
        border-radius: 5px;
        margin-top: 2rem;
        font-size: 0.8rem;
        color: {dark_color};
    }}
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {{
        background-color: {light_color} !important;
    }}
    
    /* Expander styling */
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
        logo_path = os.path.join(os.path.dirname(__file__), brand_config.get("assets", {}).get("logo_path", ""))
        
        header_html = f"""
        <div class="app-header">
        """
        
        if os.path.exists(logo_path):
            header_html += f'<img src="data:image/png;base64,{get_image_as_base64(logo_path)}" alt="{company_name} Logo">'
            
        header_html += f"""
            <div class="app-header-content">
                <h2 style="margin:0;">{company_name}</h2>
                <p style="margin:0;">Test Station Maintenance Control</p>
            </div>
        </div>
        """
        st.markdown(header_html, unsafe_allow_html=True)
    else:
        # Fallback to standard title
        st.title("Test Station Maintenance Control")
    
    st.markdown("Track and monitor the status of your test stations")
    
    # Sidebar for data loading options using an expander (hidden by default)
    with st.sidebar.expander("Data Source", expanded=False):
        uploaded_file = st.file_uploader("Upload CSV File", type="csv")
        use_sample = st.button("Load Sample Data")
        st.markdown("---")
        st.markdown("### About")
        st.markdown(
            "This app provides visualization and analysis of test station results. "
            "Upload a CSV file or use the sample data to get started."
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
        import json
        with open(os.path.join(os.path.dirname(__file__), "filter_rules.json"), "r") as f:
            filter_rules = json.load(f)
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
        # Filters
        st.header("Filters")
        
        # Update column layout to three columns (station, result multi-select, date range)
        col1, col2, col3 = st.columns(3)
        
        with col1:
            station_options = ["All Stations"] + sorted(df['stationName'].unique().tolist())
            selected_station = st.selectbox("Station Name:", station_options)
            
        with col2:
            # Use multiselect for Results; default set to include all options
            result_options = sorted(df['result'].dropna().astype(str).unique().tolist())
            selected_results = st.multiselect("Result:", result_options, default=result_options)
            
        with col3:
            try:
                dates = pd.to_datetime(df['testDate'])
                min_date = dates.min().date()
                max_date = dates.max().date()
                default_start = max_date - pd.Timedelta(days=7)
                if default_start < min_date:
                    default_start = min_date
                selected_date_range = st.date_input(
                    "Date Range:",
                    value=[default_start, max_date],
                    min_value=min_date,
                    max_value=max_date
                )
            except:
                selected_date_range = None
                st.text("Date (format issue)")
        
        # Filter the data based on selections
        filtered_df = df.copy()
        
        if selected_station != "All Stations":
            filtered_df = filtered_df[filtered_df['stationName'] == selected_station]
            
        # Apply multi-select result filter; if any selection is made, filter rows where result is in the selection
        if selected_results and set(selected_results) != set(result_options):
            filtered_df = filtered_df[filtered_df['result'].isin(selected_results)]
        
        # Remove slot filtering entirely
        
        # Range based date filtering remains unchanged
        if selected_date_range and isinstance(selected_date_range, list) and len(selected_date_range) == 2:
            start_date, end_date = selected_date_range
            filtered_df = filtered_df[pd.to_datetime(filtered_df['testDate']).dt.date.between(start_date, end_date)]
            
        # Summary metrics with enhanced styling
        st.header("Summary")
        total, passed, failed, pass_rate = create_summary_metrics(filtered_df)
        
        # Wrap metrics in a styled container
        st.markdown('<div class="metrics-container">', unsafe_allow_html=True)
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        
        with metric_col1:
            st.metric("Total Tests", total)
            
        with metric_col2:
            st.metric("Passed Tests", passed)
            
        with metric_col3:
            st.metric("Failed Tests", failed)
            
        with metric_col4:
            st.metric("Pass Rate", f"{pass_rate}%")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Visualizations
        st.header("Visualizations")
        
        if not filtered_df.empty:
            station_chart = create_station_chart(filtered_df)
            st.plotly_chart(station_chart, use_container_width=True)
        else:
            st.warning("No data available for visualization with current filters")
            
        # Data table
        st.header("Test Data")
        
        if not filtered_df.empty:
            # Style the dataframe to highlight passed/failed using brand colors
            def highlight_results(row):
                if 'PASSED' in str(row['result']):
                    return ['', f'background-color: {brand_config.get("colors", {}).get("secondary", "green")}30', '', '']
                else:
                    return ['', f'background-color: {brand_config.get("colors", {}).get("danger", "red")}30', '', '']
                
            styled_df = filtered_df.style.apply(highlight_results, axis=1)
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.warning("No data available with current filters")
        
        # Add footer with company info
        if brand_config:
            company_name = brand_config.get("company_information", {}).get("company_name", "")
            footer_html = f"""
            <div class="app-footer">
                <p>© {datetime.now().year} {company_name}. All Rights Reserved.</p>
            </div>
            """
            st.markdown(footer_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
