#!/bin/bash
set -e

echo "Starting maintenance control application..."

# Create minimal config if it doesn't exist
if [ ! -f /app/config/database_config.json ]; then
    echo "Creating minimal configuration..."
    
    # Ensure config directory exists
    mkdir -p /app/config
    
    # Create a basic config that matches docker-compose and other configs
    cat > /app/config/database_config.json << EOF
{
    "connection": {
        "type": "mysql",
        "host": "annadb",
        "port": 3306,
        "user": "annauser",
        "password": "BootMe!",
        "database": "annadb"
    },
    "query": {
        "main_query": "SELECT * FROM rig_logs", # Query rig_logs
        "custom_query_enabled": false
    },
    "column_mapping": {
        "stationName": "rig_name",          # Map from rig_logs columns
        "result": "log_result",
        "slot": "slot_number",
        "testDate": "log_upload_time",
        "lastMaintenance": "last_maintenance_date", # This column might not exist in rig_logs
        "maintenanceDue": "days_until_maintenance"  # This column might not exist in rig_logs
    }
}
EOF
    echo "Configuration created successfully"
fi

# Execute the main command
exec "$@"
