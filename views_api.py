from http import HTTPStatus
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import Response
from lnbits.core.crud import get_user
from lnbits.core.models import User
from lnbits.decorators import WalletTypeInfo, check_user_exists
from lnbits.core.services import create_invoice, pay_invoice
from lnbits.extensions.lnurlp.crud import get_pay_links, get_pay_link
from lnbits.bolt11 import decode as decode_bolt11
from loguru import logger
from typing import Optional
import shortuuid
from lnbits.decorators import require_admin_key, require_invoice_key
from lnbits.helpers import urlsafe_short_hash
from lnurl import encode as lnurl_encode

from .crud import (
    create_lnurluniversal,
    delete_lnurluniversal,
    get_lnurluniversal,
    get_lnurluniversals,
    update_lnurluniversal,
    get_lnurluniversal_balance,
    get_universal_comments,
    db
)
from .models import CreateLnurlUniversalData, LnurlUniversal
from .utils import get_withdraw_link_info
import time
import logging

lnurluniversal_api_router = APIRouter()

logging.basicConfig(level=logging.INFO)


def calculate_routing_fee_reserve(amount_sats: int) -> int:
    """Calculate appropriate fee reserve for Lightning routing.
    
    Args:
        amount_sats: The amount in satoshis to be sent
        
    Returns:
        The fee reserve in satoshis
    """
    # For small amounts, use higher percentage due to routing challenges
    if amount_sats <= 100:
        # 10% for amounts <= 100 sats
        return max(10, int(amount_sats * 0.1))
    elif amount_sats <= 1000:
        # 5% for amounts <= 1000 sats
        return max(5, int(amount_sats * 0.05))
    else:
        # 1% for larger amounts with min 10 sats
        return max(10, int(amount_sats * 0.01))


#######################################
##### ADD YOUR API ENDPOINTS HERE #####
#######################################

## Get all the records belonging to the user

@lnurluniversal_api_router.get("/api/v1/myex/lnurlp_links")
async def api_get_lnurlp_links(wallet: WalletTypeInfo = Depends(require_invoice_key)):
    try:
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
            "SELECT COUNT(*) as count FROM invoice_comments WHERE universal_id = :universal_id",
            {"universal_id": record.id}
        )
        data = record.dict()
        data['comment_count'] = comment_count['count'] if comment_count else 0
        result.append(data)

    return result

@lnurluniversal_api_router.get("/api/v1/balance/{lnurluniversal_id}")
async def api_get_balance(lnurluniversal_id: str) -> dict:
    balance = await get_lnurluniversal_balance(lnurluniversal_id)
    if balance is None:
        logger.error(f"Balance fetch failed - universal not found: {lnurluniversal_id}")
        raise HTTPException(status_code=404, detail="Not found")
    return {"balance": balance}

@lnurluniversal_api_router.get("/api/v1/lnurl/{lnurluniversal_id}")
async def api_get_lnurl(request: Request, lnurluniversal_id: str):
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
    dependencies=[Depends(require_invoice_key)],
)
async def api_lnurluniversal(lnurluniversal_id: str):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error(f"LnurlUniversal not found: {lnurluniversal_id}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Not found"
        )
    
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

@lnurluniversal_api_router.get("/api/v1/qr/{lnurluniversal_id}")
async def api_get_qr_data(request: Request, lnurluniversal_id: str):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Record not found")

    # Generate the URL to our redirect endpoint
    redirect_url = str(request.url_for(
        "lnurluniversal.api_lnurluniversal_redirect",
        lnurluniversal_id=lnurluniversal_id
    ))

    # Encode it as LNURL and add lightning: prefix
    encoded_url = "lightning:" + lnurl_encode(redirect_url)
    return Response(content=encoded_url, media_type="text/plain")



@lnurluniversal_api_router.get("/api/v1/redirect/{lnurluniversal_id}")
async def api_lnurluniversal_redirect(request: Request, lnurluniversal_id: str):
   logging.info(f"Redirect request for id: {lnurluniversal_id}")
   lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
   if not lnurluniversal:
       logger.error(f"Record not found for lnurluniversal_id: {lnurluniversal_id}")
       raise HTTPException(status_code=404, detail="Not found")

   # First check balance
   universal_balance = await get_lnurluniversal_balance(lnurluniversal_id)
   universal_balance_sats = universal_balance // 1000  # Convert to sats for comparison
   logging.info(f"Universal balance: {universal_balance} msats ({universal_balance_sats} sats)")

   # Check actual wallet balance
   from lnbits.core.crud import get_wallet
   wallet = await get_wallet(lnurluniversal.wallet)
   actual_balance = wallet.balance_msat // 1000  # Convert to sats
   logging.info(f"LNbits wallet balance: {actual_balance} sats")

   # If wallet balance is less than 60 sats AND no universal balance, force payment mode
   if actual_balance < 60 and universal_balance == 0:
       logging.info("Wallet balance below 60 sats and no universal balance, switching to payment mode")
       lnurluniversal.state = "payment"
       await update_lnurluniversal(lnurluniversal)
       
       # Handle payment case
       pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
       if not pay_link:
           logger.error(f"Payment link not found: {lnurluniversal.selectedLnurlp} for universal_id: {lnurluniversal_id}")
           raise HTTPException(status_code=404, detail="Not found")

       callback_url = str(request.url_for(
           "lnurluniversal.api_lnurl_callback",
           lnurluniversal_id=lnurluniversal_id
       ))

       return {
           "tag": "payRequest",
           "callback": callback_url,
           "minSendable": pay_link.min * 1000,
           "maxSendable": pay_link.max * 1000,
           "metadata": f'[["text/plain", "{pay_link.description}"]]'
       }

   # Continue with normal state handling
   if lnurluniversal.state == "withdraw":
       logging.info("Processing withdraw request")
       
       callback_url = str(request.url_for(
           "lnurluniversal.api_withdraw_callback",
           lnurluniversal_id=lnurluniversal_id
       ))

       # Calculate how much can be withdrawn (accounting for routing fees)
       fee_reserve = calculate_routing_fee_reserve(universal_balance_sats)
       
       if actual_balance >= (universal_balance_sats + fee_reserve):
           # Wallet has enough for full withdrawal plus fees
           max_withdrawable = universal_balance  # Already in msats
           logging.info(f"Allowing full universal balance withdrawal: {universal_balance_sats} sats (wallet has {actual_balance} sats)")
       elif actual_balance > fee_reserve + 10:  # At least 10 sats withdrawable after fees
           # Reduce withdrawable amount to leave room for fees
           max_withdrawable_sats = actual_balance - fee_reserve
           max_withdrawable = min(universal_balance, max_withdrawable_sats * 1000)  # Convert to msats
           logging.info(f"Limiting withdrawal to {max_withdrawable_sats} sats to account for {fee_reserve} sats in fees")
       else:
           # Not enough in wallet to cover universal balance
           logging.info(f"Not enough in wallet ({actual_balance} sats) to cover withdrawal of {universal_balance_sats} sats")
           # Switch to payment mode
           lnurluniversal.state = "payment"
           await update_lnurluniversal(lnurluniversal)
           
           pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
           if not pay_link:
               logger.error(f"Payment link not found: {lnurluniversal.selectedLnurlp} for universal_id: {lnurluniversal_id}")
               raise HTTPException(status_code=404, detail="Not found")

           return {
               "tag": "payRequest",
               "callback": callback_url,
               "minSendable": pay_link.min * 1000,
               "maxSendable": pay_link.max * 1000,
               "metadata": f'[["text/plain", "{pay_link.description}"]]'
           }

       return {
           "tag": "withdrawRequest",
           "callback": callback_url,
           "k1": urlsafe_short_hash(),
           "minWithdrawable": 1000,  # 1 sat minimum
           "maxWithdrawable": max_withdrawable,
           "defaultDescription": f"Withdraw from {lnurluniversal.name}"
       }
   else:
       # Handle regular payment case
       pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
       if not pay_link:
           logger.error(f"Payment link not found: {lnurluniversal.selectedLnurlp} for universal_id: {lnurluniversal_id}")
           raise HTTPException(status_code=404, detail="Not found")

       callback_url = str(request.url_for(
           "lnurluniversal.api_lnurl_callback",
           lnurluniversal_id=lnurluniversal_id
       ))

       return {
           "tag": "payRequest",
           "callback": callback_url,
           "minSendable": pay_link.min * 1000,
           "maxSendable": pay_link.max * 1000,
           "metadata": f'[["text/plain", "{pay_link.description}"]]'
       }

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/cb/{lnurluniversal_id}",
    name="lnurluniversal.api_lnurl_callback"
)
async def api_lnurl_callback(
    request: Request,
    lnurluniversal_id: str,
    amount: int = Query(...),
    comment: Optional[str] = Query(None)
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error(f"Pay callback - record not found: {lnurluniversal_id}")
        return {"status": "ERROR", "reason": "Invalid payment link"}

    pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
    if not pay_link:
        logger.error(f"Pay callback - payment link not found: {lnurluniversal.selectedLnurlp}")
        return {"status": "ERROR", "reason": "Payment setup error"}

    if comment:
        comment_id = urlsafe_short_hash()
        await db.execute(
            """
            INSERT INTO lnurluniversal.invoice_comments 
            (id, universal_id, comment, timestamp, amount)
            VALUES (:id, :universal_id, :comment, :timestamp, :amount)
            """,
            {
                "id": comment_id,
                "universal_id": lnurluniversal_id,
                "comment": comment,
                "timestamp": int(time.time()),
                "amount": amount
            }
        )

    payment = await create_invoice(
        wallet_id=pay_link.wallet,
        amount=int(amount / 1000),
        memo=f"{pay_link.description}{' - ' + comment if comment else ''}",
        extra={
            "tag": "ext_lnurluniversal",
            "universal_id": lnurluniversal_id,
            "selectedLnurlp": lnurluniversal.selectedLnurlp,
            "link": pay_link.id,
            "comment": comment if comment else None
        }
    )

    # Do not update balance here - it will be updated when payment is confirmed in tasks.py
    current_balance = await get_lnurluniversal_balance(lnurluniversal_id)

    return {
        "pr": payment.bolt11,
        "successAction": {
            "tag": "message",
            "message": "Payment received"
        },
        "routes": [],
        "balance": current_balance  # Add this line to include the balance in the response
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

  amount = decode_bolt11(pr).amount_msat // 1000  # Convert to sats
  available_balance = await get_lnurluniversal_balance(lnurluniversal_id)

  if amount > available_balance:
      return {"status": "ERROR", "reason": "Insufficient balance for withdrawal"}

  withdraw_id = urlsafe_short_hash()
  await db.execute(
      """
      INSERT INTO pending_withdrawals (id, universal_id, amount, created_time, payment_request)
      VALUES (:id, :universal_id, :amount, :created_time, :payment_request)
      """,
      {
          "id": withdraw_id,
          "universal_id": lnurluniversal_id,
          "amount": amount,
          "created_time": int(time.time()),
          "payment_request": pr
      }
  )

  try:
      # Check wallet balance to ensure we have enough for routing fees
      from lnbits.core.crud import get_wallet
      wallet = await get_wallet(lnurluniversal.wallet)
      wallet_balance_sats = wallet.balance_msat // 1000
      
      # Calculate routing fee reserve
      fee_reserve = calculate_routing_fee_reserve(amount)
      total_needed = amount + fee_reserve
      
      logging.info(f"Withdraw attempt: amount={amount} sats, wallet_balance={wallet_balance_sats} sats, fee_reserve={fee_reserve} sats, total_needed={total_needed} sats")
      
      # Check if wallet has enough balance for withdrawal + fees
      if wallet_balance_sats < total_needed:
          logger.warning(f"Insufficient wallet balance for withdrawal: wallet={wallet_balance_sats}, needed={total_needed}, universal_id={lnurluniversal_id}")
          return {
              "status": "ERROR", 
              "reason": f"Need {fee_reserve} sats extra for Lightning fees"
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
          UPDATE pending_withdrawals
          SET status = 'completed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )

      if amount >= lnurluniversal.total // 1000:
          lnurluniversal.uses += 1

      new_total = max(0, lnurluniversal.total - (amount * 1000))
      lnurluniversal.total = new_total
      if new_total == 0:
          lnurluniversal.state = "payment"
      await update_lnurluniversal(lnurluniversal)

      return {"status": "OK"}
  except Exception as e:
      await db.execute(
          """
          UPDATE pending_withdrawals
          SET status = 'failed'
          WHERE payment_request = :payment_request
          """,
          {"payment_request": pr}
      )
      # Return LNURL-compliant error response with better error messages
      error_msg = str(e).lower()
      logger.error(f"Withdrawal failed: {str(e)} universal_id={lnurluniversal_id} amount={amount}")
      
      if "no route" in error_msg:
          return {"status": "ERROR", "reason": "No route found. Try smaller amount"}
      elif "insufficient" in error_msg:
          return {"status": "ERROR", "reason": "Lightning fees too high. Try 100+ sats"}
      elif "timeout" in error_msg:
          return {"status": "ERROR", "reason": "Payment timed out. Try again"}
      else:
          # Log full error but return simple message
          logger.error(f"Unexpected withdrawal error: {str(e)}")
          return {"status": "ERROR", "reason": "Payment failed. Try again"}


# Metadata endpoint
@lnurluniversal_api_router.get("/api/v1/lnurl/{lnurluniversal_id}")
async def api_lnurl_response(request: Request, lnurluniversal_id: str):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(status_code=404, detail="Record not found")

    if lnurluniversal.state == "payment":
        pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
        if not pay_link:
            raise HTTPException(status_code=404, detail="Payment link not found")

        # Generate callback URL for this endpoint
        callback_url = str(request.url_for(
            "lnurluniversal.api_lnurl_callback",
            lnurluniversal_id=lnurluniversal_id
        ))

        # Return metadata format like LNURLP
        return {
            "callback": callback_url,
            "maxSendable": pay_link.max * 1000,
            "minSendable": pay_link.min * 1000,
            "metadata": pay_link.lnurlpay_metadata,
            "tag": "payRequest",
            "commentAllowed": pay_link.comment_chars if pay_link.comment_chars > 0 else None
        }

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
    assert lnurluniversal, "LnurlUniversal couldn't be retrieved"

    if wallet.wallet.id != lnurluniversal.wallet:
        logger.warning(f"Unauthorized access attempt to universal_id: {lnurluniversal_id} by wallet: {wallet.wallet.id}")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Forbidden"
        )

    # Update only the fields that exist in the new model
    lnurluniversal.name = data.name
    lnurluniversal.lnurlwithdrawamount = data.lnurlwithdrawamount
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
    try:
        lnurluniversal_id = urlsafe_short_hash()
        logger.info(f"Generated lnurluniversal_id: {lnurluniversal_id}")

        data.wallet = data.wallet or key_type.wallet.id
        myext = LnurlUniversal(
            id=lnurluniversal_id,
            name=data.name,
            wallet=data.wallet,
            lnurlwithdrawamount=data.lnurlwithdrawamount,
            selectedLnurlp=data.selectedLnurlp,
            selectedLnurlw=data.selectedLnurlw,
            state="payment",  # Always initialize state to "payment"
            total=0,  # Initialize total to 0
            uses=0    # Initialize uses to 0
        )

        logger.info(f"Creating LnurlUniversal with data: {myext}")

        created_lnurluniversal = await create_lnurluniversal(myext)
        logger.info(f"Created LnurlUniversal: {created_lnurluniversal}")
        
        # Fetch the created LnurlUniversal to ensure all fields are populated
        fetched_lnurluniversal = await get_lnurluniversal(created_lnurluniversal.id)
        logger.info(f"Fetched LnurlUniversal after creation: {fetched_lnurluniversal}")
        
        return fetched_lnurluniversal
    except Exception as e:
        logger.error(f"Error creating LnurlUniversal: {str(e)}")
        raise HTTPException(status_code=500, detail="Server error")


## Delete a record
@lnurluniversal_api_router.delete("/api/v1/myex/{lnurluniversal_id}")
async def api_lnurluniversal_delete(
    lnurluniversal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)

    if not lnurluniversal:
        logger.error(f"Delete failed - LnurlUniversal not found: {lnurluniversal_id}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Not found"
        )

    if lnurluniversal.wallet != wallet.wallet.id:
        logger.warning(f"Unauthorized delete attempt on universal_id: {lnurluniversal_id} by wallet: {wallet.wallet.id}")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Forbidden"
        )

    await delete_lnurluniversal(lnurluniversal_id)
    return "", HTTPStatus.NO_CONTENT


# ANY OTHER ENDPOINTS YOU NEED

## This endpoint creates a payment


@lnurluniversal_api_router.post(
    "/api/v1/myex/payment/{lnurluniversal_id}", status_code=HTTPStatus.CREATED
)
async def api_lnurluniversal_create_invoice(
    lnurluniversal_id: str, amount: int = Query(..., ge=1), memo: str = ""
) -> dict:
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)

    if not lnurluniversal:
        logger.error(f"Payment invoice creation failed - LnurlUniversal not found: {lnurluniversal_id}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Not found"
        )

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    try:
        payment = await create_invoice(
            wallet_id=lnurluniversal.wallet,
            amount=amount,
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
    universal_id: str
) -> list[dict]:
    """Get comments for a universal"""
    universal = await get_lnurluniversal(universal_id)
    if not universal:
        logger.error(f"Comments fetch - universal not found: {universal_id}")
        raise HTTPException(status_code=404, detail="Not found")

    comments = await get_universal_comments(universal_id)
    return comments

# LNURL-specific routes

