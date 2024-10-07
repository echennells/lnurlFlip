from typing import Optional, Union

from lnbits.db import Database
from lnbits.helpers import insert_query, update_query

from .models import LnurlUniversal

db = Database("ext_lnurluniversal")
table_name = "lnurluniversal.maintable"


async def create_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:
    await db.execute(
        insert_query(table_name, data),
        (*data.dict().values(),),
    )
    return data

    # this is how we used to do it

    # lnurluniversal_id = urlsafe_short_hash()
    # await db.execute(
    #     """
    #     INSERT INTO lnurluniversal.maintable
    #     (id, wallet, name, lnurlpayamount, lnurlwithdrawamount)
    #     VALUES (?, ?, ?, ?, ?)
    #     """,
    #     (
    #         lnurluniversal_id,
    #         wallet_id,
    #         data.name,
    #         data.lnurlpayamount,
    #         data.lnurlwithdrawamount,
    #     ),
    # )
    # lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    # assert lnurluniversal, "Newly created table couldn't be retrieved"


async def get_lnurluniversal(lnurluniversal_id: str) -> Optional[LnurlUniversal]:
    row = await db.fetchone(
        f"SELECT * FROM {table_name} WHERE id = ?", (lnurluniversal_id,)
    )
    return LnurlUniversal(**row) if row else None


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
        update_query(table_name, data),
        (
            *data.dict().values(),
            data.id,
        ),
    )
    return data
    # this is how we used to do it

    # q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    # await db.execute(
    #     f"UPDATE lnurluniversal.maintable SET {q} WHERE id = ?",
    #     (*kwargs.values(), lnurluniversal_id),
    # )


async def delete_lnurluniversal(lnurluniversal_id: str) -> None:
    await db.execute(f"DELETE FROM {table_name} WHERE id = ?", (lnurluniversal_id,))
