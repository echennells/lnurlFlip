from typing import Optional
from fastapi import HTTPException
from lnbits.core.crud import get_user
from lnbits.decorators import WalletTypeInfo
from lnbits.extensions.withdraw.crud import get_withdraw_link

from .crud import get_lnurluniversal
from .models import LnurlUniversal


async def check_universal_access(
    universal_id: str, 
    wallet: WalletTypeInfo,
    raise_on_error: bool = True,
    require_direct_ownership: bool = False
) -> Optional[LnurlUniversal]:
    """
    Centralized authorization check for universal access.
    
    Args:
        universal_id: The ID of the universal to check
        wallet: The wallet info from authentication
        raise_on_error: If True, raises HTTPException on access denied. 
                       If False, returns None on access denied.
        require_direct_ownership: If True, only allows direct wallet ownership (no shared wallet access).
                                 Use this for admin operations like UPDATE/DELETE.
    
    Returns:
        The universal if authorized, None if not authorized and raise_on_error=False
        
    Raises:
        HTTPException: 404 if universal not found, 403 if access denied (when raise_on_error=True)
    """
    # Get the universal
    universal = await get_lnurluniversal(universal_id)
    if not universal:
        if raise_on_error:
            raise HTTPException(status_code=404, detail="Universal not found")
        return None
    
    # Check direct ownership
    if universal.wallet == wallet.wallet.id:
        return universal
    
    # If requiring direct ownership, deny access here
    if require_direct_ownership:
        if raise_on_error:
            raise HTTPException(status_code=403, detail="Access denied - direct ownership required")
        return None
    
    # Check shared wallet access (only if not requiring direct ownership)
    user = await get_user(wallet.wallet.user)
    if user and universal.wallet in user.wallet_ids:
        return universal
    
    # Access denied
    if raise_on_error:
        raise HTTPException(status_code=403, detail="Access denied")
    return None


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
