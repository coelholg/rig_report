import csv
import mysql.connector
import argparse
import os
import json
import sys

def connect_to_database(host, port, user, password, database):
    """Connect to MySQL database"""
    try:
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            auth_plugin='mysql_native_password'
        )
        print("Connected to MySQL database")
        return connection
    except mysql.connector.Error as error:
        if "Access denied" in str(error):
            print("\nAccess Denied: Please check your username, password, and host settings.")
            print("Ensure the user has the correct privileges and the host is allowed to connect.")
        else:
            print(f"Failed to connect to MySQL database: {error}")
        return None

def read_csv_file(file_path, custom_headers=None, has_header_row=True):
    """Read CSV file and return headers and data"""
    if not os.path.exists(file_path):
        print(f"CSV file not found: {file_path}")
        return None, None
    
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            
            if has_header_row:
                # Get column names from first row
                headers = next(csv_reader)
                data = [row for row in csv_reader]
            else:
                # Use custom headers and include all rows as data
                headers = custom_headers
                data = [row for row in csv_reader]
                
            if not headers:
                print("No headers provided and CSV file has no header row")
                return None, None
                
            return headers, data
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return None, None

def create_table_if_not_exists(connection, table_name, headers, database_name):
    """
    Check if table exists. If yes, validate columns. 
    If no, create the table.
    """
    cursor = connection.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        table_exists = cursor.fetchone()
        
        if table_exists:
            print(f"Table '{table_name}' already exists. Validating columns...")
            
            # Get existing columns from the table
            cursor.execute(f"""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (database_name, table_name))
            
            existing_columns = [col[0] for col in cursor.fetchall()]
            
            # Compare existing columns (excluding 'id') with headers from config/csv
            expected_columns = set(headers)
            actual_columns = set(existing_columns)
            
            # Check if 'id' column exists (it should if created by this script)
            if 'id' in actual_columns:
                 actual_columns.remove('id') # Don't compare the auto-increment id column

            if expected_columns == actual_columns:
                print("Table columns match the expected headers.")
                return True # Table exists and columns match
            else:
                missing_in_db = list(expected_columns - actual_columns)
                extra_in_db = list(actual_columns - expected_columns)
                
                error_message = f"Column mismatch for table '{table_name}':\n"
                if missing_in_db:
                    error_message += f"  - Columns missing in database table: {missing_in_db}\n"
                if extra_in_db:
                    error_message += f"  - Unexpected columns found in database table: {extra_in_db}\n"
                error_message += "Please update the CSV/config headers or manually ALTER the table structure."
                print(error_message)
                return False # Indicate validation failure

        else:
            # Table does not exist, create it
            print(f"Table '{table_name}' does not exist. Creating...")
            # Create column definitions (all as VARCHAR by default)
            columns_sql = ', '.join([f"`{header}` VARCHAR(255)" for header in headers])
            
            create_table_query = f"""
            CREATE TABLE `{table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                {columns_sql}
            )
            """
            cursor.execute(create_table_query)
            connection.commit()
            print(f"Table '{table_name}' created successfully.")
            return True # Table created successfully

    except mysql.connector.Error as error:
        print(f"Database error during table check/creation: {error}")
        return False
    finally:
        cursor.close()

def insert_data(connection, table_name, headers, data):
    """Insert data into MySQL table"""
    if not data:
        print("No data to insert")
        return
    
    cursor = connection.cursor()
    
    # Prepare the SQL query
    placeholders = ', '.join(['%s'] * len(headers))
    columns = ', '.join([f"`{header}`" for header in headers])
    insert_query = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
    
    try:
        cursor.executemany(insert_query, data)
        connection.commit()
        print(f"{cursor.rowcount} records inserted successfully")
    except mysql.connector.Error as error:
        print(f"Failed to insert records: {error}")
    finally:
        cursor.close()

def load_config(config_file='config.json'):
    """Load configuration from JSON file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        print(f"Configuration loaded from {config_file}")
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return None

def test_connection(config_file='config.json'):
    """Test database connection using config file"""
    config = load_config(config_file)
    if not config:
        return False
    
    db_config = config.get('database', {})
    host = db_config.get('host', 'localhost')
    port = db_config.get('port', 3306)
    user = db_config.get('user', 'root')
    password = db_config.get('password', '')
    database = db_config.get('database', '')
    
    if not database:
        print("Database name not specified in config")
        return False
    
    print(f"Testing connection to {host}:{port}, user={user}, database={database}")
    conn = connect_to_database(host, port, user, password, database)
    if conn:
        conn.close()
        print("Connection successful and closed")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Import CSV data into MySQL")
    parser.add_argument("--config", default="config.json", help="Path to JSON config file")
    parser.add_argument("--csv", help="Path to CSV file (overrides config)")
    parser.add_argument("--table", help="MySQL table name (overrides config)")
    parser.add_argument("--database", help="MySQL database name (overrides config)")
    parser.add_argument("--host", help="MySQL host (overrides config)")
    parser.add_argument("--port", type=int, help="MySQL port (overrides config)")
    parser.add_argument("--user", help="MySQL username (overrides config)")
    parser.add_argument("--password", help="MySQL password (overrides config)")
    parser.add_argument("--test-connection", action="store_true", help="Only test database connection")
    
    args = parser.parse_args()
    
    # Just test connection if requested
    if args.test_connection:
        if test_connection(args.config):
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Load config from JSON file
    config = load_config(args.config)
    if not config:
        print("Failed to load configuration. Exiting...")
        return
    
    # Set parameters from config, allowing command-line arguments to override
    db_config = config.get('database', {})
    import_config = config.get('import', {})
    
    host = args.host if args.host else db_config.get('host', 'localhost')
    port = args.port if args.port else db_config.get('port', 3306)
    user = args.user if args.user else db_config.get('user', 'root')
    password = args.password if args.password else db_config.get('password', 'BootMe!')
    database = args.database if args.database else db_config.get('database')
    
    csv_file = args.csv if args.csv else import_config.get('csv_file')
    table_name = args.table if args.table else import_config.get('table_name')
    custom_headers = import_config.get('headers')
    has_header_row = import_config.get('has_header_row', True)
    
    # Validate required parameters
    if not csv_file:
        print("CSV file path not specified in config or command line")
        return
    if not table_name:
        print("Table name not specified in config or command line")
        return
    if not database:
        print("Database name not specified in config or command line")
        return
    if not has_header_row and not custom_headers:
        print("CSV file has no headers and no custom headers provided in config")
        return
    
    # Read CSV file
    headers, data = read_csv_file(csv_file, custom_headers, has_header_row)
    if not headers or data is None: # Check if data is None (error reading) or empty
        print("Failed to read CSV data or CSV is empty.")
        return
    
    # Connect to database
    connection = connect_to_database(host, port, user, password, database)
    if not connection:
        return
    
    try:
        # Create table if needed and validate columns
        if create_table_if_not_exists(connection, table_name, headers, database):
            # Only insert data if table creation/validation was successful
            insert_data(connection, table_name, headers, data)
        else:
            print("Skipping data insertion due to table validation failure.")
            
    finally:
        if connection.is_connected():
            connection.close()
            print("MySQL connection closed")

if __name__ == "__main__":
    main()
