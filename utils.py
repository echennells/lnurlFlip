from lnbits.extensions.withdraw.crud import get_withdraw_link


async def get_withdraw_link_info(withdraw_id: str):
    try:
        withdraw_link = await get_withdraw_link(withdraw_id)
        if withdraw_link:
            return {
                "id": withdraw_link.id,
                "title": withdraw_link.title,
                "min_withdrawable": withdraw_link.min_withdrawable,
                "max_withdrawable": withdraw_link.max_withdrawable,
                "uses": withdraw_link.uses,
                "wait_time": withdraw_link.wait_time,
                "is_unique": withdraw_link.is_unique,
                "unique_hash": withdraw_link.unique_hash,
                "k1": withdraw_link.k1,
                "open_time": withdraw_link.open_time,
                "used": withdraw_link.used,
                "usescsv": withdraw_link.usescsv,
                "webhook_url": withdraw_link.webhook_url,
                "custom_url": withdraw_link.custom_url
            }
        else:
            return {"error": "Withdraw link not found"}
    except Exception as e:
        return {"error": f"Error fetching withdraw link: {str(e)}"}