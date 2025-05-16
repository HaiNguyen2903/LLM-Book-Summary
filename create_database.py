import sqlite3

# Connect to a database (creates 'books.db' if it doesn't exist)
conn = sqlite3.connect('books.db')

# Create a cursor object to execute SQL commands
cursor = conn.cursor()