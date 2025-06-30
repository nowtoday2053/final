from app import app, db
from models import Campaign, Lead, Message
import sqlite3

def column_exists(conn, table, column):
    """Check if a column exists in a table"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    return any(col[1] == column for col in columns)

def table_exists(conn, table):
    """Check if a table exists in the database"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None

def migrate_database():
    """Add new columns and tables to the database"""
    with app.app_context():
        # Create a connection and get the cursor
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        
        try:
            # Add last_processed_lead_id column to campaign table if it doesn't exist
            if not column_exists(conn, 'campaign', 'last_processed_lead_id'):
                cursor.execute("""
                    ALTER TABLE campaign 
                    ADD COLUMN last_processed_lead_id INTEGER DEFAULT NULL
                """)
                print("Added last_processed_lead_id column to campaign table")
            
            # Add message_sent column to lead table if it doesn't exist
            if not column_exists(conn, 'lead', 'message_sent'):
                cursor.execute("""
                    ALTER TABLE lead
                    ADD COLUMN message_sent BOOLEAN DEFAULT 0
                """)
                print("Added message_sent column to lead table")
            
            # Add processed_at column to lead table if it doesn't exist
            if not column_exists(conn, 'lead', 'processed_at'):
                cursor.execute("""
                    ALTER TABLE lead
                    ADD COLUMN processed_at DATETIME DEFAULT NULL
                """)
                print("Added processed_at column to lead table")
            
            # Create Message table if it doesn't exist
            if not table_exists(conn, 'message'):
                cursor.execute("""
                    CREATE TABLE message (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL,
                        sender_id VARCHAR(255) NOT NULL,
                        sender_name VARCHAR(255) NOT NULL,
                        message_text TEXT NOT NULL,
                        is_read BOOLEAN DEFAULT 0,
                        ok_message_id VARCHAR(255) NOT NULL,
                        received_at DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(account_id) REFERENCES account(id)
                    )
                """)
                print("Created message table")
            
            # Handle sent_at column removal by creating a new table without it
            if column_exists(conn, 'lead', 'sent_at'):
                print("Removing sent_at column from lead table...")
                # Get all column names except sent_at
                cursor.execute("PRAGMA table_info(lead)")
                columns = [col[1] for col in cursor.fetchall() if col[1] != 'sent_at']
                columns_str = ', '.join(columns)
                
                # Create new table without sent_at
                cursor.execute(f"""
                    CREATE TABLE lead_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id INTEGER NOT NULL,
                        account_id INTEGER NOT NULL,
                        profile_url VARCHAR(255) NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        message_sent BOOLEAN DEFAULT 0,
                        processed_at DATETIME DEFAULT NULL,
                        error_message TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(campaign_id) REFERENCES campaign(id),
                        FOREIGN KEY(account_id) REFERENCES account(id)
                    )
                """)
                
                # Copy data
                cursor.execute(f"""
                    INSERT INTO lead_new ({columns_str})
                    SELECT {columns_str} FROM lead
                """)
                
                # Drop old table and rename new one
                cursor.execute("DROP TABLE lead")
                cursor.execute("ALTER TABLE lead_new RENAME TO lead")
                print("Successfully removed sent_at column")
            
            # Commit the changes
            conn.commit()
            print("Database migration completed successfully!")
            
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

if __name__ == "__main__":
    migrate_database() 