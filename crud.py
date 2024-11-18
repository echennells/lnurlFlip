"""Database operations for LnurlUniversal extension"""

from typing import Optional, Union
from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash
from loguru import logger

from .models import LnurlUniversal, CreateLnurlUniversalData

db = Database("ext_lnurluniversal")
table_name = "maintable"

async def create_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:
    try:
        data.total = 0  # Ensure total is initialized to 0
        data.uses = 0   # Ensure uses is initialized to 0
        data.state = "payment"  # Ensure initial state is set to payment
        await db.execute(
            """
            INSERT INTO lnurluniversal.maintable
            (id, name, wallet, lnurlwithdrawamount, selectedLnurlp, selectedLnurlw, state, total, uses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.id,
                data.name,
                data.wallet,
                data.lnurlwithdrawamount,
                data.selectedLnurlp,
                data.selectedLnurlw,
                data.state,
                data.total,
                data.uses
            ),
        )
        created = await get_lnurluniversal(data.id)
        return created
    except Exception as e:
        logger.error(f"Error creating LnurlUniversal in database: {str(e)}")
        raise

async def get_lnurluniversal_balance(lnurluniversal_id: str) -> int:
    """Get the balance from record and subtract pending withdrawals"""
    universal = await get_lnurluniversal(lnurluniversal_id)
    if not universal:
        return None
    # Get pending withdrawals
    pending = await db.fetchone(
        """
        SELECT COALESCE(SUM(amount), 0) as total
        FROM pending_withdrawals
        WHERE universal_id = ?
        AND status = 'pending'
        """,
        (lnurluniversal_id,)
    )
    pending_amount = pending["total"] if pending else 0
    available_balance = max(0, universal.total - pending_amount)
    return available_balance

async def get_lnurluniversal(lnurluniversal_id: str) -> Optional[LnurlUniversal]:
    row = await db.fetchone(
        f"SELECT * FROM {table_name} WHERE id = ?", (lnurluniversal_id,)
    )
    if row:
        lnurluniversal = LnurlUniversal(**row)
        return lnurluniversal
    else:
        logger.warning(f"LnurlUniversal not found for id: {lnurluniversal_id}")
        return None

async def get_lnurluniversals(wallet_ids: Union[str, list[str]]) -> list[LnurlUniversal]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM {table_name} WHERE wallet IN ({q})", (*wallet_ids,)
    )
    return [LnurlUniversal(**row) for row in rows]


async def update_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:

    await db.execute(
        """
        UPDATE lnurluniversal.maintable
        SET name = ?,
            wallet = ?,
            lnurlwithdrawamount = ?,
            selectedLnurlp = ?,
            selectedLnurlw = ?,
            state = ?,
            total = ?,
            uses = ?
        WHERE id = ?
        """,
        (
            data.name,
            data.wallet,
            data.lnurlwithdrawamount,
            data.selectedLnurlp,
            data.selectedLnurlw,
            data.state,
            data.total,
            data.uses,
            data.id,
        ),
    )
    return data


async def delete_lnurluniversal(lnurluniversal_id: str) -> None:
    await db.execute(f"DELETE FROM {table_name} WHERE id = ?", (lnurluniversal_id,))

async def get_universal_comments(universal_id: str) -> list[dict]:
    """Get all comments for a universal"""
    rows = await db.fetchall(
        """
        SELECT id, comment, timestamp, amount
        FROM invoice_comments
        WHERE universal_id = ?
        ORDER BY timestamp DESC
        """,
        (universal_id,)
    )
    return [
        {
            "id": row["id"],
            "comment": row["comment"],
            "timestamp": row["timestamp"],
            "amount": row["amount"]
        }
        for row in rows
    ]
