-- Grant privileges to 'annauser' from any host ('%')
GRANT ALL PRIVILEGES ON annadb.* TO 'annauser'@'%';
FLUSH PRIVILEGES;

-- Optional: If you want to be more restrictive, you could grant from the Docker network subnet
-- Example: GRANT ALL PRIVILEGES ON annadb.* TO 'annauser'@'172.19.0.%';
-- FLUSH PRIVILEGES;
