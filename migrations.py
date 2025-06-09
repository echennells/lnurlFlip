# Migration file for lnurluniversal extension

async def m001_initial(db):
    """
    Create initial tables with complete schema
    """
    # Create main table
    await db.execute(
        f"""
        CREATE TABLE lnurluniversal.maintable (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            wallet TEXT NOT NULL,
            selectedLnurlp TEXT NOT NULL,
            selectedLnurlw TEXT NOT NULL,
            total_msat {db.big_int} NOT NULL DEFAULT 0,
            uses {db.big_int} NOT NULL DEFAULT 0
        );
        """
    )
    
    # Create pending withdrawals table
    await db.execute(
        f"""
        CREATE TABLE lnurluniversal.pending_withdrawals (
            id TEXT PRIMARY KEY,
            universal_id TEXT NOT NULL REFERENCES {db.references_schema}maintable (id),
            amount_msat {db.big_int} NOT NULL,
            status TEXT DEFAULT 'pending',
            created_time {db.big_int} NOT NULL,
            payment_request TEXT NOT NULL
        );
        """
    )
    
    # Create invoice comments table
    await db.execute(
        f"""
        CREATE TABLE lnurluniversal.invoice_comments (
            id TEXT PRIMARY KEY,
            universal_id TEXT NOT NULL REFERENCES {db.references_schema}maintable (id),
            comment TEXT NOT NULL,
            timestamp {db.big_int} NOT NULL,
            amount_msat {db.big_int} NOT NULL
        );
        """
    )
    
    # Create indexes
    await db.execute(
        "CREATE INDEX idx_pending_withdrawals_universal_id ON lnurluniversal.pending_withdrawals(universal_id)"
    )
    await db.execute(
        "CREATE INDEX idx_pending_withdrawals_status ON lnurluniversal.pending_withdrawals(status)"
    )
    await db.execute(
        "CREATE INDEX idx_invoice_comments_universal_id ON lnurluniversal.invoice_comments(universal_id)"
    )