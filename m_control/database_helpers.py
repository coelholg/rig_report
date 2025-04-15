import pandas as pd
import json
from pathlib import Path
import streamlit as st
import os

# Database connection imports
import mysql.connector
from mysql.connector import Error
import sqlite3
try:
    import psycopg2
except ImportError:
    pass  # PostgreSQL driver optional

def get_config_path():
    """Get the path to the database configuration file"""
    possible_paths = [
        Path(__file__).parent / "config" / "database_config.json",
        Path("config/database_config.json"),
        Path("./config/database_config.json")
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None

def load_config():
    """Load the database configuration from JSON file"""
    config_path = get_config_path()
    
    if not config_path:
        # Try loading from the main config.json if database_config.json doesn't exist
        config_path = Path(__file__).parent / "config.json"
        if not config_path.exists():
            return None
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # If config already has connection key, use it directly
        if 'connection' in config:
            conn = config['connection']
        else:
            # Get database config from old format and ensure it has all required fields
            conn = config.get('database', {})
        
        # Check for environment variables and override config
        if os.environ.get('DB_HOST'):
            conn['host'] = os.environ.get('DB_HOST')
        if os.environ.get('DB_PORT'):
            conn['port'] = int(os.environ.get('DB_PORT'))
        if os.environ.get('DB_USER'):
            conn['user'] = os.environ.get('DB_USER')
        if os.environ.get('DB_PASSWORD'):
            conn['password'] = os.environ.get('DB_PASSWORD')
        if os.environ.get('DB_NAME'):
            conn['database'] = os.environ.get('DB_NAME')
        if os.environ.get('DB_TYPE'):
            conn['type'] = os.environ.get('DB_TYPE')
        elif 'type' not in conn:
            conn['type'] = 'mysql'  # Default to MySQL if not specified
        
        # Return full config including query and column mapping if they exist
        result = {'connection': conn}
        if 'query' in config:
            result['query'] = config['query']
        if 'column_mapping' in config:
            result['column_mapping'] = config['column_mapping']
        
        # Add debug mode flag for connection troubleshooting
        result['debug'] = os.environ.get('DB_DEBUG', 'false').lower() == 'true'
        
        return result
    except Exception as e:
        print(f"Error loading database config: {e}")
        return None

def get_connection(conn_params):
    """Create database connection based on connection parameters"""
    db_type = conn_params.get('type', '').lower()
    debug = conn_params.get('debug', False)
    
    try:
        if db_type == 'mysql':
            if debug:
                print(f"Connecting to MySQL at {conn_params.get('host')}:{conn_params.get('port', 3306)} with user '{conn_params.get('user')}'")
            
            connection = mysql.connector.connect(
                host=conn_params.get('host'),
                port=conn_params.get('port', 3306),
                user=conn_params.get('user'),
                password=conn_params.get('password'),
                database=conn_params.get('database')
            )
            if debug:
                print("MySQL connection successful!")
            return connection
        elif db_type == 'postgresql':
            return psycopg2.connect(
                host=conn_params.get('host'),
                port=conn_params.get('port', 5432),
                user=conn_params.get('user'),
                password=conn_params.get('password'),
                database=conn_params.get('database')
            )
        elif db_type == 'sqlite':
            # For SQLite, the host parameter is the file path
            db_path = conn_params.get('host')
            return sqlite3.connect(db_path)
        else:
            print(f"Unsupported database type: {db_type}")
            return None
    except mysql.connector.Error as err:
        if err.errno == 1045:  # Access denied error
            print("Authentication Error: Check your username and password")
            print(f"Details: {err}")
            print("TIP: Ensure the user has proper grants and can connect from this host")
        elif err.errno == 2003:  # Can't connect to MySQL server
            print(f"Connection Error: Cannot connect to server at {conn_params.get('host')}:{conn_params.get('port', 3306)}")
            print("TIP: Check if the server is running and network connectivity")
        elif err.errno == 1049:  # Unknown database
            print(f"Database Error: Unknown database '{conn_params.get('database')}'")
            print("TIP: Create the database first or check the database name")
        else:
            print(f"MySQL Error ({err.errno}): {err}")
        
        if debug:
            print(f"Connection parameters: {conn_params}")
        return None
    except Exception as e:
        print(f"Error connecting to {db_type} database: {e}")
        if debug:
            print(f"Connection parameters: {conn_params}")
        return None

def execute_query(query, params=None):
    """Execute a query and return results as DataFrame"""
    config = load_config()
    if not config:
        return None, "Database configuration not found"
    
    conn_params = config.get('connection', {})
    conn = get_connection(conn_params)
    
    if not conn:
        return None, f"Could not connect to database"
    
    try:
        # Execute query and get results
        if params:
            df = pd.read_sql(query, conn, params=params)
        else:
            df = pd.read_sql(query, conn)
        
        # Close connection
        conn.close()
        
        return df, None
    except Exception as e:
        if conn:
            conn.close()
        return None, f"Error executing query: {str(e)}"

def test_connection():
    """Test database connection and return status"""
    config = load_config()
    if not config:
        return False, "Database configuration not found"
    
    conn_params = config.get('connection', {})
    conn = get_connection(conn_params)
    
    if conn:
        conn.close()
        return True, "Connection successful"
    else:
        return False, "Failed to establish connection"

def test_database_credentials():
    """Test database credentials specifically to diagnose connection issues"""
    config = load_config()
    if not config:
        return False, "Database configuration not found"
    
    conn_params = config.get('connection', {})
    db_type = conn_params.get('type', '').lower()
    
    # Force debug mode for detailed output
    debug_params = conn_params.copy()
    debug_params['debug'] = True
    
    try:
        print(f"\n===== Testing {db_type.upper()} Database Connection =====")
        print(f"Host: {debug_params.get('host')}")
        print(f"Port: {debug_params.get('port', 3306 if db_type == 'mysql' else 5432)}")
        print(f"User: {debug_params.get('user')}")
        print(f"Database: {debug_params.get('database')}")
        print("Password: [HIDDEN]")
        
        conn = get_connection(debug_params)
        
        if conn:
            print("✅ Connection successful!")
            
            # Test if we can execute a simple query
            cursor = conn.cursor()
            if db_type == 'mysql':
                cursor.execute("SELECT VERSION()")
            elif db_type == 'postgresql':
                cursor.execute("SELECT version()")
            elif db_type == 'sqlite':
                cursor.execute("SELECT sqlite_version()")
                
            version = cursor.fetchone()
            print(f"Server version: {version[0]}")
            
            cursor.close()
            conn.close()
            return True, "Connection and query test successful"
        else:
            print("❌ Connection failed")
            return False, "Failed to establish database connection"
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        return False, f"Connection test error: {str(e)}"

def initialize_database():
    """Initialize database tables if they don't exist"""
    config = load_config()
    if not config:
        return False, "Database configuration not found"
    
    conn_params = config.get('connection', {})
    if not conn_params:
        return False, "No connection parameters found in configuration"
        
    conn = get_connection(conn_params)
    
    if not conn:
        return False, "Could not connect to database"
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Check if maintenance_control table exists
        if conn_params.get('type') == 'mysql':
            # First check if database exists
            db_name = conn_params.get('database', 'annadb')
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            cursor.execute(f"USE {db_name}")
            
            # Check for maintenance_control table
            cursor.execute("SHOW TABLES LIKE 'maintenance_control'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Create the maintenance_control table
                create_table_sql = """
                CREATE TABLE maintenance_control (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    stationName VARCHAR(255) NOT NULL,
                    slot VARCHAR(50) NOT NULL,
                    maintenanceDate DATETIME,
                    scheduledDate DATETIME,
                    maintenanceBy VARCHAR(255),
                    status VARCHAR(50) NOT NULL DEFAULT 'Scheduled',
                    notes TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_station_slot (stationName, slot),
                    INDEX idx_status (status),
                    INDEX idx_timestamp (timestamp)
                )
                """
                cursor.execute(create_table_sql)
                conn.commit()
                
                # Insert sample maintenance data
                sample_data_sql = """
                INSERT INTO maintenance_control 
                (stationName, slot, maintenanceDate, scheduledDate, maintenanceBy, status, notes)
                VALUES 
                ('Station A', 'Slot 1', DATE_SUB(NOW(), INTERVAL 15 DAY), DATE_ADD(NOW(), INTERVAL 15 DAY), 'System', 'Scheduled', 'Initial maintenance record'),
                ('Station B', 'Slot 2', DATE_SUB(NOW(), INTERVAL 25 DAY), DATE_ADD(NOW(), INTERVAL 5 DAY), 'System', 'Due Soon', 'Initial maintenance record'),
                ('Station C', 'Slot 1', DATE_SUB(NOW(), INTERVAL 35 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY), 'System', 'Overdue', 'Initial maintenance record')
                """
                cursor.execute(sample_data_sql)
                conn.commit()
                
            # Check if rig_logs table exists
            cursor.execute("SHOW TABLES LIKE 'rig_logs'")
            rig_logs_exists = cursor.fetchone()
            
            if not rig_logs_exists:
                # Create the rig_logs table with updated schema
                create_rig_logs_sql = """
                CREATE TABLE rig_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    rig_name VARCHAR(255) NOT NULL,
                    log_result VARCHAR(50) NOT NULL,
                    slot_number VARCHAR(50) NOT NULL,
                    tlog_upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_maintenance_date DATETIME,
                    days_until_maintenance INT,
                    cycle_count INT DEFAULT 0,
                    maintenance_status VARCHAR(50),
                    scheduled_date DATETIME,
                    INDEX idx_rig_slot (rig_name, slot_number),
                    INDEX idx_upload_time (tlog_upload_time)
                )
                """
                cursor.execute(create_rig_logs_sql)
                conn.commit()
                
                # Insert sample rig logs data with maintenance info
                sample_logs_sql = """
                INSERT INTO rig_logs 
                (rig_name, log_result, slot_number, tlog_upload_time, last_maintenance_date, days_until_maintenance, cycle_count, maintenance_status, scheduled_date)
                VALUES 
                ('Station A', 'PASSED', 'Slot 1', NOW(), DATE_SUB(NOW(), INTERVAL 15 DAY), 15, 100, 'OK', DATE_ADD(NOW(), INTERVAL 15 DAY)),
                ('Station B', 'FAILED', 'Slot 2', NOW(), DATE_SUB(NOW(), INTERVAL 25 DAY), 5, 200, 'Due Soon', DATE_ADD(NOW(), INTERVAL 5 DAY)),
                ('Station C', 'PASSED', 'Slot 1', NOW(), DATE_SUB(NOW(), INTERVAL 35 DAY), -5, 300, 'Overdue', DATE_SUB(NOW(), INTERVAL 5 DAY))
                """
                cursor.execute(sample_logs_sql)
                conn.commit()
                
        conn.close()
        return True, "Database initialized successfully"
    except Exception as e:
        if conn:
            if cursor:
                cursor.close()
            conn.close()
        return False, f"Error initializing database: {str(e)}"





