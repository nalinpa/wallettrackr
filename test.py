from pymongo import MongoClient

# Simple connection without authentication
client = MongoClient('mongodb://localhost:27018/crypto_tracker')

# Test the connection
try:
    # This will force a connection
    client.admin.command('ping')
    print("Connected successfully!")
    print("Databases:", client.list_database_names())
except Exception as e:
    print(f"Connection failed: {e}")