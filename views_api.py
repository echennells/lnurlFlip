from http import HTTPStatus
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import Response
from lnbits.core.crud import get_user
from lnbits.core.models import User
from lnbits.decorators import WalletTypeInfo, check_user_exists
from lnbits.core.services import create_invoice, pay_invoice
from lnbits.core.crud import get_wallet
from lnbits.extensions.lnurlp.crud import get_pay_link
from lnbits.bolt11 import decode as decode_bolt11
from loguru import logger
from typing import Optional
from lnbits.decorators import require_admin_key, require_invoice_key
from lnbits.helpers import urlsafe_short_hash
from lnurl import encode as lnurl_encode

# Balance constants (in millisatoshis)
MIN_WITHDRAWABLE_MSAT = 50000       # 50 sats minimum withdrawable amount

from .crud import (
    create_lnurlflip,
    delete_lnurlFlip,
    get_lnurlFlip,
    get_lnurlFlips,
    update_lnurlFlip,
    get_lnurlflip_balance,
    get_flip_comments,
    check_duplicate_name,
    process_payment_with_lock,
    db
)
from .models import CreateLnurlFlipData, LnurlFlip
from .utils import get_withdraw_link_info
import time
import logging

lnurlFlip_api_router = APIRouter()

logging.basicConfig(level=logging.INFO)


async def create_payment_response(request: Request, lnurlflip_id: str, pay_link) -> dict:
    """Create a standardized LNURL payment response."""
    callback_url = str(request.url_for(
        "lnurlFlip.api_lnurl_callback",
        lnurlflip_id=lnurlflip_id
    ))
    
    return {
        "tag": "payRequest",
        "callback": callback_url,
        "minSendable": int(pay_link.min) * 1000,
        "maxSendable": int(pay_link.max) * 1000,
        "metadata": f'[["text/plain", "{pay_link.description}"]]'
    }






#######################################
##### ADD YOUR API ENDPOINTS HERE #####
#######################################

## Get all the records belonging to the user

@lnurlFlip_api_router.get("/api/v1/myex/lnurlp_links")
async def api_get_lnurlp_links(wallet: WalletTypeInfo = Depends(require_invoice_key)):
    try:
        from lnbits.extensions.lnurlp.crud import get_pay_links
        pay_links = await get_pay_links(wallet_ids=[wallet.wallet.id])

        formatted_links = [
            {
                "id": link.id,
                "description": link.description,
                "amount": f"{link.min} - {link.max} sats" if link.min != link.max else f"{link.min} sats",
                "lnurl": link.lnurl
            }
            for link in pay_links
        ]

        return {"pay_links": formatted_links}
    except Exception as e:
        logger.error(f"Error in api_get_lnurlp_links: {str(e)}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Server error"
        )

@lnurlFlip_api_router.get("/api/v1/lnurlFlip/withdraw/{withdraw_id}")
async def api_get_withdraw_link(withdraw_id: str, user: User = Depends(check_user_exists)):
    withdraw_info = await get_withdraw_link_info(withdraw_id)
    if "error" in withdraw_info:
        logger.error(f"Withdraw link not found: {withdraw_id}, error: {withdraw_info['error']}")
        raise HTTPException(status_code=404, detail="Not found")
    return withdraw_info

@lnurlFlip_api_router.get("/api/v1/myex", status_code=HTTPStatus.OK)
async def api_lnurlFlips(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(require_invoice_key),
):
    wallet_ids = [wallet.wallet.id]
    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    records = await get_lnurlFlips(wallet_ids)
    result = []

    for record in records:
        # Get comment count for each record
        comment_count = await db.fetchone(
            "SELECT COUNT(*) as count FROM lnurlFlip.invoice_comments WHERE flip_id = :flip_id",
            {"flip_id": record.id}
        )
        data = record.dict()
        data['comment_count'] = comment_count['count'] if comment_count else 0
        result.append(data)

    return result

@lnurlFlip_api_router.get("/api/v1/balance/{lnurlflip_id}")
async def api_get_balance(
    lnurlflip_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> dict:
    flip = await get_lnurlFlip(lnurlflip_id)
    if not flip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this flip
    if flip.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or flip.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    balance = await get_lnurlflip_balance(lnurlflip_id)
    return {"balance": balance}

@lnurlFlip_api_router.get("/api/v1/lnurl/{lnurlflip_id}")
async def api_get_lnurl(
    request: Request, 
    lnurlflip_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    flip = await get_lnurlFlip(lnurlflip_id)
    if not flip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this flip
    if flip.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or flip.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Just construct the URL directly
    base_url = str(request.base_url).rstrip('/')
    redirect_url = f"{base_url}/lnurlFlip/api/v1/redirect/{lnurlflip_id}"

    logging.info(f"Redirect URL before encoding: {redirect_url}")

    encoded_url = "lightning:" + lnurl_encode(redirect_url)
    logging.info(f"EncodedURL: {encoded_url}")
    return Response(content=encoded_url, media_type="text/plain")

## Get a single record


@lnurlFlip_api_router.get(
    "/api/v1/myex/{lnurlflip_id}",
    status_code=HTTPStatus.OK,
)
async def api_lnurlFlip(
    lnurlflip_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    lnurlflip = await get_lnurlFlip(lnurlflip_id)
    if not lnurlflip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this flip
    if lnurlflip.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or lnurlflip.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Add balance and comment count like the list endpoint
    balance = await get_lnurlflip_balance(lnurlflip_id)
    comment_count = await db.fetchone(
        "SELECT COUNT(*) as count FROM lnurlFlip.invoice_comments WHERE flip_id = :flip_id",
        {"flip_id": lnurlflip_id}
    )
    
    data = lnurlflip.dict()
    data['balance'] = balance
    data['comment_count'] = comment_count['count'] if comment_count else 0
    return data




@lnurlFlip_api_router.get("/api/v1/redirect/{lnurlflip_id}")
async def api_lnurlflip_redirect(request: Request, lnurlflip_id: str):
   logging.info(f"Redirect request for id: {lnurlflip_id}")
   lnurlflip = await get_lnurlFlip(lnurlflip_id)
   if not lnurlflip:
       logger.error(f"Record not found for lnurlflip_id: {lnurlflip_id}")
       raise HTTPException(status_code=404, detail="Not found")

   # Get balance information (all balances in msats for consistency)
   flip_balance_msat = await get_lnurlflip_balance(lnurlflip_id)

   # Check actual wallet balance
   from lnbits.core.crud import get_wallet
   wallet = await get_wallet(lnurlflip.wallet)
   actual_balance_msat = wallet.balance_msat

   # Simplified state determination logic:
   # Use withdraw mode only if flip has withdrawable balance
   # and wallet can cover the withdrawal
   can_withdraw = (
       flip_balance_msat >= MIN_WITHDRAWABLE_MSAT and  # Has minimum withdrawable balance
       actual_balance_msat >= flip_balance_msat  # Wallet can cover the withdrawal
   )
   
   # Log the decision
   mode = "withdraw" if can_withdraw else "payment"
   logger.debug(f"Using {mode} mode - flip: {flip_balance_msat // 1000} sats, wallet: {actual_balance_msat // 1000} sats")
   
   # Generate appropriate response based on withdrawal capability
   if not can_withdraw:
       # Payment mode response
       pay_link = await get_pay_link(lnurlflip.selectedLnurlp)
       if not pay_link:
           logger.error(f"Payment link not found: {lnurlflip.selectedLnurlp} for flip_id: {lnurlflip_id}")
           raise HTTPException(status_code=404, detail="Not found")
       
       return await create_payment_response(request, lnurlflip_id, pay_link)
   else:
       # Withdraw mode response
       
       # Get withdraw link configuration
       withdraw_info = await get_withdraw_link_info(lnurlflip.selectedLnurlw)
       if "error" in withdraw_info:
           logger.error(f"Withdraw link not found: {lnurlflip.selectedLnurlw} for flip_id: {lnurlflip_id}")
           raise HTTPException(status_code=404, detail="Withdraw link not found")
       
       callback_url = str(request.url_for(
           "lnurlFlip.api_withdraw_callback",
           lnurlflip_id=lnurlflip_id
       ))
       
       # Use withdraw link's configured limits (converting from sats to msats)
       min_withdrawable_msat = withdraw_info["min_withdrawable"] * 1000
       max_withdrawable_msat = withdraw_info["max_withdrawable"] * 1000
       
       
       # Apply constraints: flip balance and wallet balance
       # First, limit to flip balance
       effective_max_msat = min(max_withdrawable_msat, flip_balance_msat)
       
       # Then, ensure we don't exceed available wallet balance
       if effective_max_msat > actual_balance_msat:
           effective_max_msat = max(0, actual_balance_msat)
           
       max_withdrawable_msat = effective_max_msat
       
       logger.info(f"Withdraw limits for {lnurlflip_id[:8]}... - min: {min_withdrawable_msat // 1000} sats, max: {max_withdrawable_msat // 1000} sats")
       
       return {
           "tag": "withdrawRequest",
           "callback": callback_url,
           "k1": urlsafe_short_hash(),
           "minWithdrawable": min_withdrawable_msat,
           "maxWithdrawable": max_withdrawable_msat,
           "defaultDescription": f"Withdraw from {lnurlflip.name}"
       }

@lnurlFlip_api_router.get(
    "/api/v1/lnurl/cb/{lnurlflip_id}",
    name="lnurlFlip.api_lnurl_callback"
)
async def api_lnurl_callback(
    request: Request,
    lnurlflip_id: str,
    amount: int = Query(...),
    comment: Optional[str] = Query(None, max_length=500, regex="^[^<>]*$")
):
    lnurlflip = await get_lnurlFlip(lnurlflip_id)
    if not lnurlflip:
        logger.error(f"Pay callback - record not found: {lnurlflip_id}")
        return {"status": "ERROR", "reason": "Invalid payment link"}

    pay_link = await get_pay_link(lnurlflip.selectedLnurlp)
    if not pay_link:
        logger.error(f"Pay callback - payment link not found: {lnurlflip.selectedLnurlp}")
        return {"status": "ERROR", "reason": "Payment setup error"}
    
    logger.debug(f"Payment link {pay_link.id} for flip {lnurlflip_id[:8]}...")
    
    # Validate that the wallet exists
    wallet = await get_wallet(pay_link.wallet)
    if not wallet:
        logger.error(f"Wallet not found: {pay_link.wallet}")
        return {"status": "ERROR", "reason": "Wallet configuration error"}
    
    logger.debug(f"Using wallet {wallet.id} with balance {wallet.balance_msat // 1000} sats")
    logger.info(f"Wallet found - ID: {wallet.id}, Name: {wallet.name}, Balance: {wallet.balance_msat} msats")
    
    # Check funding source
    from lnbits.wallets import get_funding_source
    funding_source = get_funding_source()
    logger.info(f"Funding source: {type(funding_source).__name__}")

    if comment:
        comment_id = urlsafe_short_hash()
        await db.execute(
            """
            INSERT INTO lnurlFlip.invoice_comments 
            (id, flip_id, comment, timestamp, amount_msat)
            VALUES (:id, :flip_id, :comment, :timestamp, :amount_msat)
            """,
            {
                "id": comment_id,
                "flip_id": lnurlflip_id,
                "comment": comment,
                "timestamp": int(time.time()),
                "amount_msat": amount  # Amount in msats from LNURL
            }
        )

    
    try:
        payment = await create_invoice(
            wallet_id=pay_link.wallet,
            amount=amount // 1000,  # Convert from msats to sats for invoice creation
            memo=f"{pay_link.description}{' - ' + comment if comment else ''}",
            extra={
                "tag": "ext_lnurlflip",
                "flip_id": lnurlflip_id,
                "selectedLnurlp": lnurlflip.selectedLnurlp,
                "link": pay_link.id,
                "comment": comment if comment else None
            }
        )
        
        if not payment or not payment.bolt11:
            logger.error(f"Invoice creation failed - no payment object returned")
            return {"status": "ERROR", "reason": "Failed to create invoice"}
            
    except Exception as e:
        logger.error(f"Exception creating invoice: {str(e)}")
        return {"status": "ERROR", "reason": f"Invoice creation error: {str(e)}"}

    # Do not update balance here - it will be updated when payment is confirmed in tasks.py
    current_balance = await get_lnurlflip_balance(lnurlflip_id)
    
    logger.info(f"Created invoice for flip {lnurlflip_id[:8]}... amount: {amount // 1000} sats, hash: {payment.payment_hash[:8]}...")

    return {
        "pr": payment.bolt11,
        "successAction": {
            "tag": "message",
            "message": "Payment received!"
        },
        "routes": []
    }


@lnurlFlip_api_router.get(
  "/api/v1/lnurl/withdraw/cb/{lnurlflip_id}",
  name="lnurlFlip.api_withdraw_callback"
)

async def api_withdraw_callback(
  request: Request,
  lnurlflip_id: str,
  k1: str = Query(...),
  pr: str = Query(...)
):
  lnurlflip = await get_lnurlFlip(lnurlflip_id)
  if not lnurlflip:
      return {"status": "ERROR", "reason": "Record not found"}

  # Get withdraw link configuration to validate limits
  withdraw_info = await get_withdraw_link_info(lnurlflip.selectedLnurlw)
  if "error" in withdraw_info:
      logger.error(f"Withdraw link not found: {lnurlflip.selectedLnurlw} for flip_id: {lnurlflip_id}")
      return {"status": "ERROR", "reason": "Withdraw link configuration error"}

  amount_msat = decode_bolt11(pr).amount_msat  # Amount from invoice in msats
  available_balance_msat = await get_lnurlflip_balance(lnurlflip_id)  # Balance in msats

  # Check against withdraw link limits
  min_withdrawable_msat = withdraw_info["min_withdrawable"] * 1000
  max_withdrawable_msat = withdraw_info["max_withdrawable"] * 1000
  
  # Apply the same constraint as in the initial request: limit to flip balance
  effective_max_msat = min(max_withdrawable_msat, available_balance_msat)
  
  if amount_msat < min_withdrawable_msat:
      return {"status": "ERROR", "reason": f"Amount below minimum: {min_withdrawable_msat // 1000} sats"}
  
  if amount_msat > effective_max_msat:
      return {"status": "ERROR", "reason": f"Amount exceeds maximum: {effective_max_msat // 1000} sats"}

  if amount_msat > available_balance_msat:
      return {"status": "ERROR", "reason": "Insufficient balance for withdrawal"}

  withdraw_id = urlsafe_short_hash()
  await db.execute(
      """
      INSERT INTO lnurlFlip.pending_withdrawals (id, flip_id, amount_msat, created_time, payment_request)
      VALUES (:id, :flip_id, :amount_msat, :created_time, :payment_request)
      """,
      {
          "id": withdraw_id,
          "flip_id": lnurlflip_id,
          "amount_msat": amount_msat,  # Store amount in msats
          "created_time": int(time.time()),
          "payment_request": pr
      }
  )

  try:
      # Check wallet balance to ensure we have enough
      from lnbits.core.crud import get_wallet
      wallet = await get_wallet(lnurlflip.wallet)
      wallet_balance_msat = wallet.balance_msat
      
      logging.info(f"Withdraw attempt: amount={amount_msat} msat, wallet_balance={wallet_balance_msat} msat")
      
      # Check if wallet has enough balance for withdrawal
      if wallet_balance_msat < amount_msat:
          logger.warning(f"Insufficient wallet balance for withdrawal: wallet={wallet_balance_msat}, amount={amount_msat}, flip_id={lnurlflip_id}")
          return {
              "status": "ERROR", 
              "reason": "Insufficient balance"
          }
      
      payment_hash = await pay_invoice(
          wallet_id=lnurlflip.wallet,
          payment_request=pr,
          extra={
              "tag": "ext_lnurlflip",
              "lnurlwithdraw": True,
              "flip_id": lnurlflip_id,
              "selectedLnurlw": lnurlflip.selectedLnurlw,
              "withdraw_id": withdraw_id
          }
      )
      # Withdrawal processed

      await db.execute(
          """
          UPDATE lnurlFlip.pending_withdrawals
          SET status = 'completed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )

      # Use locked payment processing to prevent race conditions
      increment_uses = amount_msat >= lnurlflip.total_msat
      updated_flip = await process_payment_with_lock(
          lnurlflip_id,
          -amount_msat,  # Negative because we're withdrawing
          increment_uses=increment_uses,
          operation_type="withdrawal"
      )

      return {"status": "OK"}
  except Exception as e:
      await db.execute(
          """
          UPDATE lnurlFlip.pending_withdrawals
          SET status = 'failed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )
      # Log full error for debugging
      logger.error(f"Withdrawal failed: {str(e)} flip_id={lnurlflip_id} amount_msat={amount_msat}")
      # Return simple LNURL-compliant error response
      return {"status": "ERROR", "reason": "Payment failed"}


@lnurlFlip_api_router.put("/api/v1/myex/{lnurlflip_id}")
async def api_lnurlFlip_update(
    data: CreateLnurlFlipData,
    lnurlflip_id: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> LnurlFlip:
    if not lnurlflip_id:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Not found"
        )
    
    lnurlflip = await get_lnurlflip(lnurlflip_id)
    if not lnurlflip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Admin operations require direct wallet ownership
    if lnurlflip.wallet != wallet.wallet.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for duplicate name if the name is being changed
    if lnurlflip.name != data.name:
        if await check_duplicate_name(data.name, lnurlflip.wallet, exclude_id=lnurlflip_id):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"A lnurlflip with the name '{data.name}' already exists in this wallet"
            )

    # Update only the fields that exist in the new model
    lnurlflip.name = data.name
    lnurlflip.selectedLnurlp = data.selectedLnurlp
    lnurlflip.selectedLnurlw = data.selectedLnurlw

    return await update_lnurlFlip(lnurlflip)


## Create a new record

@lnurlFlip_api_router.post("/api/v1/myex", status_code=HTTPStatus.CREATED)
async def api_lnurlflip_create(
    request: Request,
    data: CreateLnurlFlipData,
    key_type: WalletTypeInfo = Depends(require_admin_key),
) -> LnurlFlip:
    data.wallet = data.wallet or key_type.wallet.id
    
    # Check for duplicate name
    if await check_duplicate_name(data.name, data.wallet):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"A lnurlflip with the name '{data.name}' already exists in this wallet"
        )
    
    lnurlflip_id = urlsafe_short_hash()
    myext = LnurlFlip(
        id=lnurlflip_id,
        name=data.name,
        wallet=data.wallet,
        selectedLnurlp=data.selectedLnurlp,
        selectedLnurlw=data.selectedLnurlw,
        total_msat=0,  # Initialize total to 0
        uses=0    # Initialize uses to 0
    )

    created_lnurlflip = await create_lnurlflip(myext)
    
    # Fetch the created LnurlFlip to ensure all fields are populated
    fetched_lnurlflip = await get_lnurlFlip(created_lnurlflip.id)
    logger.info(f"Created flip {created_lnurlflip.id} with name: {created_lnurlflip.name}")
    
    return fetched_lnurlflip


## Delete a record
@lnurlFlip_api_router.delete("/api/v1/myex/{lnurlflip_id}")
async def api_lnurlflip_delete(
    lnurlflip_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    lnurlflip = await get_lnurlflip(lnurlflip_id)
    if not lnurlflip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Admin operations require direct wallet ownership
    if lnurlflip.wallet != wallet.wallet.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await delete_lnurlFlip(lnurlflip_id)
    return "", HTTPStatus.NO_CONTENT


# ANY OTHER ENDPOINTS YOU NEED

## This endpoint creates a payment


@lnurlFlip_api_router.post(
    "/api/v1/myex/payment/{lnurlflip_id}", status_code=HTTPStatus.CREATED
)
async def api_lnurlflip_create_invoice(
    lnurlflip_id: str, 
    amount: int = Query(..., ge=1),  # Amount in sats
    memo: str = "",
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> dict:
    lnurlflip = await get_lnurlflip(lnurlflip_id)
    if not lnurlflip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if lnurlflip.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or lnurlflip.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    try:
        payment = await create_invoice(
            wallet_id=lnurlflip.wallet,
            amount=amount,  # Already in sats, no conversion needed
            memo=f"{memo} to {lnurlflip.name}" if memo else f"{lnurlflip.name}",
            extra={
                "tag": "lnurlflip",
                "amount": amount,
            },
        )
    except Exception as exc:
        logger.error(f"Payment creation failed for flip_id: {lnurlflip_id}, error: {str(exc)}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Payment creation failed"
        ) from exc

    return {"payment_hash": payment.payment_hash, "payment_request": payment.bolt11}

@lnurlFlip_api_router.get("/api/v1/comments/{flip_id}")
async def api_get_comments(
    flip_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> list[dict]:
    """Get comments for a flip"""
    flip = await get_lnurlFlip(flip_id)
    if not flip:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this flip
    if flip.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or flip.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")

    comments = await get_flip_comments(flip_id)
    return comments

# LNURL-specific routes

