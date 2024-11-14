# the migration file is where you build your database tables
# If you create a new release for your extension ,
# remember the migration file is like a blockchain, never edit only add!


async def m001_initial(db):
    """
    Initial templates table.
    """
    await db.execute(
        """
        CREATE TABLE lnurluniversal.maintable (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            total INTEGER DEFAULT 0,
            lnurlpayamount INTEGER DEFAULT 0,
            lnurlwithdrawamount INTEGER DEFAULT 0,
            lnurlwithdraw TEXT,
            lnurlpay TEXT
        );
    """
    )

async def m002_update_schema(db):
    """
    Updates table structure to new schema.
    """
    # First create a backup of existing data
    await db.execute(
        """
        CREATE TEMPORARY TABLE lnurluniversal_backup AS
        SELECT id, wallet, name
        FROM lnurluniversal.maintable;
        """
    )

    # Drop the existing table
    await db.execute("DROP TABLE lnurluniversal.maintable;")

    # Create the new table with updated schema
    await db.execute(
        """
        CREATE TABLE lnurluniversal.maintable (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            wallet TEXT NOT NULL,
            lnurlwithdrawamount INTEGER,
            selectedLnurlp TEXT NOT NULL,
            selectedLnurlw TEXT NOT NULL
        );
        """
    )

    # Restore the backed up data with default values for new fields
    await db.execute(
        """
        INSERT INTO lnurluniversal.maintable (id, name, wallet, lnurlwithdrawamount, selectedLnurlp, selectedLnurlw)
        SELECT
            id,
            name,
            wallet,
            NULL as lnurlwithdrawamount,
            '' as selectedLnurlp,
            '' as selectedLnurlw
        FROM lnurluniversal_backup;
        """
    )

    # Drop the temporary backup table
    await db.execute("DROP TABLE lnurluniversal_backup;")

async def m003_add_state(db):
    """
    Add state column to maintable.
    """
    await db.execute(
        """
        ALTER TABLE lnurluniversal.maintable 
        ADD COLUMN state TEXT NOT NULL DEFAULT 'inactive';
        """
    )

async def m004_add_total(db):
    """
    Add total column back to maintable.
    """
    await db.execute(
        """
        ALTER TABLE lnurluniversal.maintable
        ADD COLUMN total INTEGER NOT NULL DEFAULT 0;
        """
    )
    return balance

# Add to migrations.py
async def m005_add_pending_withdrawals(db):
    """
    Add pending withdrawals table
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS lnurluniversal.pending_withdrawals (
            id TEXT PRIMARY KEY,
            universal_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_time INTEGER NOT NULL,
            payment_request TEXT NOT NULL,
            FOREIGN KEY (universal_id) REFERENCES maintable(id)
        );
        """
    )

async def m007_add_uses(db):
    """
    Add uses column to maintable to track deposit/withdrawal cycles
    """
    await db.execute(
        """
        ALTER TABLE lnurluniversal.maintable
        ADD COLUMN uses INTEGER NOT NULL DEFAULT 0;
        """
    )

async def m008_add_comments(db):
    """
    Add comments table for LNURL-pay comments
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS lnurluniversal.invoice_comments (
            id TEXT PRIMARY KEY,
            universal_id TEXT NOT NULL,
            comment TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            FOREIGN KEY (universal_id) REFERENCES maintable(id)
        );
        """
    )
