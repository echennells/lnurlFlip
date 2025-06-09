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
MIN_WALLET_BALANCE_MSAT = 50000     # 50 sats minimum wallet balance for withdraw mode
MIN_WITHDRAWABLE_MSAT = 50000       # 50 sats minimum withdrawable amount

from .crud import (
    create_lnurluniversal,
    delete_lnurluniversal,
    get_lnurluniversal,
    get_lnurluniversals,
    update_lnurluniversal,
    get_lnurluniversal_balance,
    get_universal_comments,
    check_duplicate_name,
    process_payment_with_lock,
    db
)
from .models import CreateLnurlUniversalData, LnurlUniversal
from .utils import get_withdraw_link_info
import time
import logging

lnurluniversal_api_router = APIRouter()

logging.basicConfig(level=logging.INFO)


async def create_payment_response(request: Request, lnurluniversal_id: str, pay_link) -> dict:
    """Create a standardized LNURL payment response."""
    callback_url = str(request.url_for(
        "lnurluniversal.api_lnurl_callback",
        lnurluniversal_id=lnurluniversal_id
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

@lnurluniversal_api_router.get("/api/v1/myex/lnurlp_links")
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

@lnurluniversal_api_router.get("/api/v1/lnurluniversal/withdraw/{withdraw_id}")
async def api_get_withdraw_link(withdraw_id: str, user: User = Depends(check_user_exists)):
    withdraw_info = await get_withdraw_link_info(withdraw_id)
    if "error" in withdraw_info:
        logger.error(f"Withdraw link not found: {withdraw_id}, error: {withdraw_info['error']}")
        raise HTTPException(status_code=404, detail="Not found")
    return withdraw_info

@lnurluniversal_api_router.get("/api/v1/myex", status_code=HTTPStatus.OK)
async def api_lnurluniversals(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(require_invoice_key),
):
    wallet_ids = [wallet.wallet.id]
    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    records = await get_lnurluniversals(wallet_ids)
    result = []

    for record in records:
        # Get comment count for each record
        comment_count = await db.fetchone(
            "SELECT COUNT(*) as count FROM lnurluniversal.invoice_comments WHERE universal_id = :universal_id",
            {"universal_id": record.id}
        )
        data = record.dict()
        data['comment_count'] = comment_count['count'] if comment_count else 0
        result.append(data)

    return result

@lnurluniversal_api_router.get("/api/v1/balance/{lnurluniversal_id}")
async def api_get_balance(
    lnurluniversal_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> dict:
    universal = await get_lnurluniversal(lnurluniversal_id)
    if not universal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if universal.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or universal.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    balance = await get_lnurluniversal_balance(lnurluniversal_id)
    return {"balance": balance}

@lnurluniversal_api_router.get("/api/v1/lnurl/{lnurluniversal_id}")
async def api_get_lnurl(
    request: Request, 
    lnurluniversal_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    universal = await get_lnurluniversal(lnurluniversal_id)
    if not universal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if universal.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or universal.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Just construct the URL directly
    base_url = str(request.base_url).rstrip('/')
    redirect_url = f"{base_url}/lnurluniversal/api/v1/redirect/{lnurluniversal_id}"

    logging.info(f"Redirect URL before encoding: {redirect_url}")

    encoded_url = "lightning:" + lnurl_encode(redirect_url)
    logging.info(f"EncodedURL: {encoded_url}")
    return Response(content=encoded_url, media_type="text/plain")

## Get a single record


@lnurluniversal_api_router.get(
    "/api/v1/myex/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
)
async def api_lnurluniversal(
    lnurluniversal_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if lnurluniversal.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or lnurluniversal.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Add balance and comment count like the list endpoint
    balance = await get_lnurluniversal_balance(lnurluniversal_id)
    comment_count = await db.fetchone(
        "SELECT COUNT(*) as count FROM lnurluniversal.invoice_comments WHERE universal_id = :universal_id",
        {"universal_id": lnurluniversal_id}
    )
    
    data = lnurluniversal.dict()
    data['balance'] = balance
    data['comment_count'] = comment_count['count'] if comment_count else 0
    return data




@lnurluniversal_api_router.get("/api/v1/redirect/{lnurluniversal_id}")
async def api_lnurluniversal_redirect(request: Request, lnurluniversal_id: str):
   logging.info(f"Redirect request for id: {lnurluniversal_id}")
   lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
   if not lnurluniversal:
       logger.error(f"Record not found for lnurluniversal_id: {lnurluniversal_id}")
       raise HTTPException(status_code=404, detail="Not found")

   # Get balance information (all balances in msats for consistency)
   universal_balance_msat = await get_lnurluniversal_balance(lnurluniversal_id)
   logging.info(f"Universal balance: {universal_balance_msat} msats ({universal_balance_msat // 1000} sats)")

   # Check actual wallet balance
   from lnbits.core.crud import get_wallet
   wallet = await get_wallet(lnurluniversal.wallet)
   actual_balance_msat = wallet.balance_msat
   logging.info(f"LNbits wallet balance: {actual_balance_msat} msats ({actual_balance_msat // 1000} sats)")

   # Simplified state determination logic:
   # Use withdraw mode only if we have sufficient balance
   # Otherwise, use payment mode
   can_withdraw = (
       universal_balance_msat >= MIN_WITHDRAWABLE_MSAT and  # Has minimum withdrawable balance
       actual_balance_msat >= MIN_WITHDRAWABLE_MSAT  # Wallet has enough balance
   )
   
   # Log the decision
   if can_withdraw:
       logging.info(f"Can withdraw: universal balance {universal_balance_msat // 1000} sats, wallet balance {actual_balance_msat // 1000} sats")
   else:
       logging.info(f"Cannot withdraw: universal balance {universal_balance_msat // 1000} sats, wallet balance {actual_balance_msat // 1000} sats")
   
   # Generate appropriate response based on withdrawal capability
   if not can_withdraw:
       # Payment mode response
       pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
       if not pay_link:
           logger.error(f"Payment link not found: {lnurluniversal.selectedLnurlp} for universal_id: {lnurluniversal_id}")
           raise HTTPException(status_code=404, detail="Not found")
       
       return await create_payment_response(request, lnurluniversal_id, pay_link)
   else:
       # Withdraw mode response
       logging.info("Processing withdraw request")
       
       # Get withdraw link configuration
       withdraw_info = await get_withdraw_link_info(lnurluniversal.selectedLnurlw)
       if "error" in withdraw_info:
           logger.error(f"Withdraw link not found: {lnurluniversal.selectedLnurlw} for universal_id: {lnurluniversal_id}")
           raise HTTPException(status_code=404, detail="Withdraw link not found")
       
       callback_url = str(request.url_for(
           "lnurluniversal.api_withdraw_callback",
           lnurluniversal_id=lnurluniversal_id
       ))
       
       # Use withdraw link's configured limits (converting from sats to msats)
       min_withdrawable_msat = withdraw_info["min_withdrawable"] * 1000
       max_withdrawable_msat = withdraw_info["max_withdrawable"] * 1000
       
       logging.info(f"Withdraw link configured limits - min: {min_withdrawable_msat // 1000} sats, max: {max_withdrawable_msat // 1000} sats")
       
       # Apply constraints: universal balance and wallet balance
       # First, limit to universal balance
       effective_max_msat = min(max_withdrawable_msat, universal_balance_msat)
       logging.info(f"After applying universal balance constraint: max = {effective_max_msat // 1000} sats")
       
       # Then, ensure we don't exceed available wallet balance
       if effective_max_msat > actual_balance_msat:
           effective_max_msat = max(0, actual_balance_msat)
           logging.info(f"Further limiting withdrawal to {effective_max_msat // 1000} sats due to wallet balance")
       
       max_withdrawable_msat = effective_max_msat
       
       logging.info(f"Final withdraw limits - min: {min_withdrawable_msat // 1000} sats, max: {max_withdrawable_msat // 1000} sats")
       
       return {
           "tag": "withdrawRequest",
           "callback": callback_url,
           "k1": urlsafe_short_hash(),
           "minWithdrawable": min_withdrawable_msat,
           "maxWithdrawable": max_withdrawable_msat,
           "defaultDescription": f"Withdraw from {lnurluniversal.name}"
       }

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/cb/{lnurluniversal_id}",
    name="lnurluniversal.api_lnurl_callback"
)
async def api_lnurl_callback(
    request: Request,
    lnurluniversal_id: str,
    amount: int = Query(...),
    comment: Optional[str] = Query(None, max_length=500, regex="^[^<>]*$")
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error(f"Pay callback - record not found: {lnurluniversal_id}")
        return {"status": "ERROR", "reason": "Invalid payment link"}

    pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
    if not pay_link:
        logger.error(f"Pay callback - payment link not found: {lnurluniversal.selectedLnurlp}")
        return {"status": "ERROR", "reason": "Payment setup error"}
    
    # Add wallet comparison logging
    logger.info(f"Wallet comparison - Universal wallet: {lnurluniversal.wallet}, PayLink wallet: {pay_link.wallet}")
    logger.info(f"Universal ID: {lnurluniversal_id}, PayLink ID: {pay_link.id}")
    
    # Validate that the wallet exists
    wallet = await get_wallet(pay_link.wallet)
    if not wallet:
        logger.error(f"Wallet not found: {pay_link.wallet}")
        return {"status": "ERROR", "reason": "Wallet configuration error"}
    logger.info(f"Wallet found - ID: {wallet.id}, Name: {wallet.name}, Balance: {wallet.balance_msat} msats")
    
    # Check funding source
    from lnbits.wallets import get_funding_source
    funding_source = get_funding_source()
    logger.info(f"Funding source: {type(funding_source).__name__}")

    if comment:
        comment_id = urlsafe_short_hash()
        await db.execute(
            """
            INSERT INTO lnurluniversal.invoice_comments 
            (id, universal_id, comment, timestamp, amount_msat)
            VALUES (:id, :universal_id, :comment, :timestamp, :amount_msat)
            """,
            {
                "id": comment_id,
                "universal_id": lnurluniversal_id,
                "comment": comment,
                "timestamp": int(time.time()),
                "amount_msat": amount  # Amount in msats from LNURL
            }
        )

    # Log invoice creation details
    logger.info(f"Creating invoice - Amount requested: {amount} msats ({amount // 1000} sats)")
    logger.info(f"Invoice wallet: {pay_link.wallet}")
    logger.info(f"Invoice memo: {pay_link.description}{' - ' + comment if comment else ''}")
    
    try:
        payment = await create_invoice(
            wallet_id=pay_link.wallet,
            amount=amount // 1000,  # Convert from msats to sats for invoice creation
            memo=f"{pay_link.description}{' - ' + comment if comment else ''}",
            extra={
                "tag": "ext_lnurluniversal",
                "universal_id": lnurluniversal_id,
                "selectedLnurlp": lnurluniversal.selectedLnurlp,
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
    current_balance = await get_lnurluniversal_balance(lnurluniversal_id)
    
    logger.info(f"Created invoice for universal {lnurluniversal_id}: payment_hash={payment.payment_hash}, amount={amount // 1000} sats")
    logger.info(f"Invoice extra data: {payment.extra}")
    
    # Decode and log invoice details for debugging
    try:
        decoded = decode_bolt11(payment.bolt11)
        logger.info(f"Decoded invoice - Amount: {decoded.amount_msat} msats, Description: {decoded.description}")
        logger.info(f"Invoice payment_hash: {decoded.payment_hash}")
        logger.info(f"Invoice payee: {decoded.payee if hasattr(decoded, 'payee') else 'Not specified'}")
        logger.info(f"Invoice expiry: {decoded.expiry} seconds")
        logger.info(f"Full bolt11 invoice: {payment.bolt11}")
    except Exception as e:
        logger.error(f"Failed to decode created invoice: {str(e)}")

    return {
        "pr": payment.bolt11,
        "successAction": {
            "tag": "message",
            "message": "Payment received!"
        },
        "routes": []
    }


@lnurluniversal_api_router.get(
  "/api/v1/lnurl/withdraw/cb/{lnurluniversal_id}",
  name="lnurluniversal.api_withdraw_callback"
)

async def api_withdraw_callback(
  request: Request,
  lnurluniversal_id: str,
  k1: str = Query(...),
  pr: str = Query(...)
):
  lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
  if not lnurluniversal:
      return {"status": "ERROR", "reason": "Record not found"}

  # Get withdraw link configuration to validate limits
  withdraw_info = await get_withdraw_link_info(lnurluniversal.selectedLnurlw)
  if "error" in withdraw_info:
      logger.error(f"Withdraw link not found: {lnurluniversal.selectedLnurlw} for universal_id: {lnurluniversal_id}")
      return {"status": "ERROR", "reason": "Withdraw link configuration error"}

  amount_msat = decode_bolt11(pr).amount_msat  # Amount from invoice in msats
  available_balance_msat = await get_lnurluniversal_balance(lnurluniversal_id)  # Balance in msats

  # Check against withdraw link limits
  min_withdrawable_msat = withdraw_info["min_withdrawable"] * 1000
  max_withdrawable_msat = withdraw_info["max_withdrawable"] * 1000
  
  # Apply the same constraint as in the initial request: limit to universal balance
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
      INSERT INTO lnurluniversal.pending_withdrawals (id, universal_id, amount_msat, created_time, payment_request)
      VALUES (:id, :universal_id, :amount_msat, :created_time, :payment_request)
      """,
      {
          "id": withdraw_id,
          "universal_id": lnurluniversal_id,
          "amount_msat": amount_msat,  # Store amount in msats
          "created_time": int(time.time()),
          "payment_request": pr
      }
  )

  try:
      # Check wallet balance to ensure we have enough
      from lnbits.core.crud import get_wallet
      wallet = await get_wallet(lnurluniversal.wallet)
      wallet_balance_msat = wallet.balance_msat
      
      logging.info(f"Withdraw attempt: amount={amount_msat} msat, wallet_balance={wallet_balance_msat} msat")
      
      # Check if wallet has enough balance for withdrawal
      if wallet_balance_msat < amount_msat:
          logger.warning(f"Insufficient wallet balance for withdrawal: wallet={wallet_balance_msat}, amount={amount_msat}, universal_id={lnurluniversal_id}")
          return {
              "status": "ERROR", 
              "reason": "Insufficient balance"
          }
      
      payment_hash = await pay_invoice(
          wallet_id=lnurluniversal.wallet,
          payment_request=pr,
          extra={
              "tag": "ext_lnurluniversal",
              "lnurlwithdraw": True,
              "universal_id": lnurluniversal_id,
              "selectedLnurlw": lnurluniversal.selectedLnurlw,
              "withdraw_id": withdraw_id
          }
      )
      # Withdrawal processed

      await db.execute(
          """
          UPDATE lnurluniversal.pending_withdrawals
          SET status = 'completed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )

      # Use locked payment processing to prevent race conditions
      increment_uses = amount_msat >= lnurluniversal.total_msat
      updated_universal = await process_payment_with_lock(
          lnurluniversal_id,
          -amount_msat,  # Negative because we're withdrawing
          increment_uses=increment_uses,
          operation_type="withdrawal"
      )

      return {"status": "OK"}
  except Exception as e:
      await db.execute(
          """
          UPDATE lnurluniversal.pending_withdrawals
          SET status = 'failed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )
      # Return LNURL-compliant error response with better error messages
      error_msg = str(e).lower()
      logger.error(f"Withdrawal failed: {str(e)} universal_id={lnurluniversal_id} amount_msat={amount_msat}")
      
      if "no route" in error_msg:
          return {"status": "ERROR", "reason": "No route found. Try smaller amount"}
      elif "insufficient" in error_msg:
          return {"status": "ERROR", "reason": "Insufficient balance"}
      elif "timeout" in error_msg:
          return {"status": "ERROR", "reason": "Payment timed out. Try again"}
      else:
          # Log full error but return simple message
          logger.error(f"Unexpected withdrawal error: {str(e)}")
          return {"status": "ERROR", "reason": "Payment failed. Try again"}


@lnurluniversal_api_router.put("/api/v1/myex/{lnurluniversal_id}")
async def api_lnurluniversal_update(
    data: CreateLnurlUniversalData,
    lnurluniversal_id: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> LnurlUniversal:
    if not lnurluniversal_id:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Not found"
        )
    
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Admin operations require direct wallet ownership
    if lnurluniversal.wallet != wallet.wallet.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for duplicate name if the name is being changed
    if lnurluniversal.name != data.name:
        if await check_duplicate_name(data.name, lnurluniversal.wallet, exclude_id=lnurluniversal_id):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"A lnurluniversal with the name '{data.name}' already exists in this wallet"
            )

    # Update only the fields that exist in the new model
    lnurluniversal.name = data.name
    lnurluniversal.lnurlwithdrawamount_sat = data.lnurlwithdrawamount_sat
    lnurluniversal.selectedLnurlp = data.selectedLnurlp
    lnurluniversal.selectedLnurlw = data.selectedLnurlw

    return await update_lnurluniversal(lnurluniversal)


## Create a new record

@lnurluniversal_api_router.post("/api/v1/myex", status_code=HTTPStatus.CREATED)
async def api_lnurluniversal_create(
    request: Request,
    data: CreateLnurlUniversalData,
    key_type: WalletTypeInfo = Depends(require_admin_key),
) -> LnurlUniversal:
    data.wallet = data.wallet or key_type.wallet.id
    
    # Check for duplicate name
    if await check_duplicate_name(data.name, data.wallet):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"A lnurluniversal with the name '{data.name}' already exists in this wallet"
        )
    
    lnurluniversal_id = urlsafe_short_hash()
    logger.info(f"Generated lnurluniversal_id: {lnurluniversal_id}")
    myext = LnurlUniversal(
        id=lnurluniversal_id,
        name=data.name,
        wallet=data.wallet,
        lnurlwithdrawamount_sat=data.lnurlwithdrawamount_sat,
        selectedLnurlp=data.selectedLnurlp,
        selectedLnurlw=data.selectedLnurlw,
        state="payment",  # Always initialize state to "payment"
        total_msat=0,  # Initialize total to 0
        uses=0    # Initialize uses to 0
    )

    logger.info(f"Creating LnurlUniversal with data: {myext}")

    created_lnurluniversal = await create_lnurluniversal(myext)
    logger.info(f"Created LnurlUniversal: {created_lnurluniversal}")
    
    # Fetch the created LnurlUniversal to ensure all fields are populated
    fetched_lnurluniversal = await get_lnurluniversal(created_lnurluniversal.id)
    logger.info(f"Fetched LnurlUniversal after creation: {fetched_lnurluniversal}")
    
    return fetched_lnurluniversal


## Delete a record
@lnurluniversal_api_router.delete("/api/v1/myex/{lnurluniversal_id}")
async def api_lnurluniversal_delete(
    lnurluniversal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Admin operations require direct wallet ownership
    if lnurluniversal.wallet != wallet.wallet.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await delete_lnurluniversal(lnurluniversal_id)
    return "", HTTPStatus.NO_CONTENT


# ANY OTHER ENDPOINTS YOU NEED

## This endpoint creates a payment


@lnurluniversal_api_router.post(
    "/api/v1/myex/payment/{lnurluniversal_id}", status_code=HTTPStatus.CREATED
)
async def api_lnurluniversal_create_invoice(
    lnurluniversal_id: str, 
    amount: int = Query(..., ge=1),  # Amount in sats
    memo: str = "",
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> dict:
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if lnurluniversal.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or lnurluniversal.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    try:
        payment = await create_invoice(
            wallet_id=lnurluniversal.wallet,
            amount=amount,  # Already in sats, no conversion needed
            memo=f"{memo} to {lnurluniversal.name}" if memo else f"{lnurluniversal.name}",
            extra={
                "tag": "lnurluniversal",
                "amount": amount,
            },
        )
    except Exception as exc:
        logger.error(f"Payment creation failed for universal_id: {lnurluniversal_id}, error: {str(exc)}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Payment creation failed"
        ) from exc

    return {"payment_hash": payment.payment_hash, "payment_request": payment.bolt11}

@lnurluniversal_api_router.get("/api/v1/comments/{universal_id}")
async def api_get_comments(
    universal_id: str,
    wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> list[dict]:
    """Get comments for a universal"""
    universal = await get_lnurluniversal(universal_id)
    if not universal:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if user has access to this universal
    if universal.wallet != wallet.wallet.id:
        user = await get_user(wallet.wallet.user)
        if not user or universal.wallet not in user.wallet_ids:
            raise HTTPException(status_code=403, detail="Access denied")

    comments = await get_universal_comments(universal_id)
    return comments

# LNURL-specific routes

