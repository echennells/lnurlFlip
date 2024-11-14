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
from lnbits.decorators import get_key_type, require_admin_key, require_invoice_key
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


#######################################
##### ADD YOUR API ENDPOINTS HERE #####
#######################################

## Get all the records belonging to the user

@lnurluniversal_api_router.get("/api/v1/myex/lnurlp_links")
async def api_get_lnurlp_links(wallet: WalletTypeInfo = Depends(get_key_type)):
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
        print(f"Error in api_get_lnurlp_links: {str(e)}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Error fetching LNURL Pay links: {str(e)}"
        )

@lnurluniversal_api_router.get("/api/v1/lnurluniversal/withdraw/{withdraw_id}")
async def api_get_withdraw_link(withdraw_id: str, user: User = Depends(check_user_exists)):
    withdraw_info = await get_withdraw_link_info(withdraw_id)
    if "error" in withdraw_info:
        raise HTTPException(status_code=404, detail=withdraw_info["error"])
    return withdraw_info

@lnurluniversal_api_router.get("/api/v1/myex", status_code=HTTPStatus.OK)
async def api_lnurluniversals(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(get_key_type),
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
            "SELECT COUNT(*) as count FROM invoice_comments WHERE universal_id = ?",
            (record.id,)
        )
        data = record.dict()
        data['comment_count'] = comment_count['count'] if comment_count else 0
        result.append(data)

    return result

@lnurluniversal_api_router.get("/api/v1/balance/{lnurluniversal_id}")
async def api_get_balance(lnurluniversal_id: str) -> dict:
    """Get the current balance (received - withdrawn) for a lnurluniversal entry"""
    try:
        balance = await get_lnurluniversal_balance(lnurluniversal_id)
        return {
            "id": lnurluniversal_id,
            "balance": balance,
            "unit": "satoshis"
        }
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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


#@lnurluniversal_api_router.get(
#    "/api/v1/myex/{lnurluniversal_id}",
#    status_code=HTTPStatus.OK,
#    dependencies=[Depends(require_invoice_key)],
#)
#async def api_lnurluniversal(lnurluniversal_id: str):
#    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
#    if not lnurluniversal:
#        raise HTTPException(
#            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
#        )
#    return lnurluniversal.dict()

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

#@lnurluniversal_api_router.get(
#   "/api/v1/redirect/{lnurluniversal_id}",
#   name="lnurluniversal.api_lnurluniversal_redirect"
#)


@lnurluniversal_api_router.get("/api/v1/redirect/{lnurluniversal_id}")
async def api_lnurluniversal_redirect(request: Request, lnurluniversal_id: str):
   logging.info(f"Redirect request for id: {lnurluniversal_id}")
   lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
   if not lnurluniversal:
       raise HTTPException(status_code=404, detail="Record not found")

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
           raise HTTPException(status_code=404, detail="Payment link not found")

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

       # Calculate how much can be withdrawn
       if actual_balance >= (universal_balance_sats + 50):
           # Plenty of balance, allow full universal balance withdrawal
           max_withdrawable = universal_balance  # Already in msats
           logging.info(f"Allowing full universal balance withdrawal: {universal_balance_sats} sats")
       elif actual_balance >= universal_balance_sats:
           # Can cover universal balance but will go below reserve, allow it anyway
           max_withdrawable = universal_balance  # Already in msats
           logging.info(f"Allowing full universal balance withdrawal (below reserve): {universal_balance_sats} sats")
       else:
           # Not enough in wallet to cover universal balance
           logging.info(f"Not enough in wallet ({actual_balance} sats) to cover withdrawal of {universal_balance_sats} sats")
           # Switch to payment mode
           lnurluniversal.state = "payment"
           await update_lnurluniversal(lnurluniversal)
           
           pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
           if not pay_link:
               raise HTTPException(status_code=404, detail="Payment link not found")

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
           raise HTTPException(status_code=404, detail="Payment link not found")

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
    logger.info(f"Callback received with amount: {amount} for id: {lnurluniversal_id}")
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error("Universal not found")
        raise HTTPException(status_code=404, detail="Record not found")

    logger.info(f"Universal state: {lnurluniversal.state}")
    logger.info(f"Current total: {lnurluniversal.total}")

    pay_link = await get_pay_link(lnurluniversal.selectedLnurlp)
    if not pay_link:
        raise HTTPException(status_code=404, detail="Payment link not found")

    if comment:
        logger.info(f"Comment received: {comment}")
        
        # Store the comment in the database
        comment_id = urlsafe_short_hash()
        await db.execute(
            """
            INSERT INTO lnurluniversal.invoice_comments 
            (id, universal_id, comment, timestamp, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                comment_id,
                lnurluniversal_id,
                comment,
                int(time.time()),
                amount
            )
        )

    # Create invoice with tracking data
    payment_hash, payment_request = await create_invoice(
        wallet_id=pay_link.wallet,
        amount=int(amount / 1000),  # Convert msats to sats
        memo=f"{pay_link.description}{' - ' + comment if comment else ''}",  # Add comment to memo if present
        extra={
            "tag": "ext_lnurluniversal",
            "universal_id": lnurluniversal_id,
            "selectedLnurlp": lnurluniversal.selectedLnurlp,
            "link": pay_link.id,
            "comment": comment if comment else None
        }
    )

    # Update the total immediately
    new_total = lnurluniversal.total + amount
    lnurluniversal.total = new_total
    lnurluniversal.state = "withdraw" if new_total > 0 else "payment"
    await update_lnurluniversal(lnurluniversal)
    
    logger.info(f"Updated total: {new_total}")
    logger.info(f"Updated state: {lnurluniversal.state}")

    # Fetch the updated lnurluniversal to confirm changes
    updated_lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    logger.info(f"Confirmed total after update: {updated_lnurluniversal.total}")
    logger.info(f"Confirmed state after update: {updated_lnurluniversal.state}")

    # Calculate and return the current balance
    current_balance = await get_lnurluniversal_balance(lnurluniversal_id)
    logger.info(f"Current balance: {current_balance}")

    return {
        "pr": payment_request,
        "successAction": {
            "tag": "message",
            "message": f"Payment received. Current balance: {current_balance / 1000} sats"
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
  logger.info("-------- WITHDRAW CALLBACK START --------")
  logger.info(f"Withdraw callback received for {lnurluniversal_id}")

  lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
  if not lnurluniversal:
      raise HTTPException(status_code=404, detail="Record not found")

  # Extract amount from payment request
  amount = decode_bolt11(pr).amount_msat // 1000  # Convert to sats
  logger.info(f"Withdraw amount requested: {amount} sats")

  # Check current available balance
  available_balance = await get_lnurluniversal_balance(lnurluniversal_id)
  logger.info(f"Current available balance: {available_balance} sats")

  if amount > available_balance:
      raise HTTPException(status_code=400, detail="Insufficient balance for withdrawal")

  # Add pending withdrawal
  withdraw_id = urlsafe_short_hash()
  logger.info(f"Creating pending withdrawal record with ID: {withdraw_id}")

  await db.execute(
      """
      INSERT INTO pending_withdrawals (id, universal_id, amount, created_time, payment_request)
      VALUES (?, ?, ?, ?, ?)
      """,
      (withdraw_id, lnurluniversal_id, amount, int(time.time()), pr)
  )

  try:
      # Pay the invoice
      logger.info(f"Attempting to pay withdrawal invoice for {amount} sats")
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
      logger.info(f"Payment successful with hash: {payment_hash}")

      # Mark withdrawal as completed
      await db.execute(
          """
          UPDATE pending_withdrawals
          SET status = 'completed'
          WHERE payment_request = ?
          """,
          (pr,)
      )

      # If this withdrawal brings balance to 0, increment uses
      if amount >= lnurluniversal.total // 1000:  # Convert msats to sats for comparison
          logger.info("Withdrawal brings balance to 0, incrementing uses")
          lnurluniversal.uses += 1

      # Update universal total and state
      new_total = max(0, lnurluniversal.total - (amount * 1000))
      lnurluniversal.total = new_total
      if new_total == 0:
          lnurluniversal.state = "payment"
      await update_lnurluniversal(lnurluniversal)

      logger.info(f"Updated balance after withdrawal: {new_total // 1000} sats")
      logger.info(f"Updated uses count: {lnurluniversal.uses}")
      logger.info("-------- WITHDRAW CALLBACK END --------")
      return {"status": "OK"}
  except Exception as e:
      # Mark withdrawal as failed
      await db.execute(
          """
          UPDATE pending_withdrawals
          SET status = 'failed'
          WHERE payment_request = ?
          """,
          (pr,)
      )
      logger.error(f"Failed to pay withdraw invoice: {str(e)}")
      logger.info("-------- WITHDRAW CALLBACK END WITH ERROR --------")
      raise HTTPException(status_code=500, detail=str(e))


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
    wallet: WalletTypeInfo = Depends(get_key_type),
) -> LnurlUniversal:
    if not lnurluniversal_id:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    assert lnurluniversal, "LnurlUniversal couldn't be retrieved"

    if wallet.wallet.id != lnurluniversal.wallet:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your LnurlUniversal."
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
        raise HTTPException(status_code=500, detail=f"Error creating LnurlUniversal: {str(e)}")


## Delete a record
@lnurluniversal_api_router.delete("/api/v1/myex/{lnurluniversal_id}")
async def api_lnurluniversal_delete(
    lnurluniversal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)

    if not lnurluniversal:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )

    if lnurluniversal.wallet != wallet.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your LnurlUniversal."
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
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    try:
        payment_hash, payment_request = await create_invoice(
            wallet_id=lnurluniversal.wallet,
            amount=amount,
            memo=f"{memo} to {lnurluniversal.name}" if memo else f"{lnurluniversal.name}",
            extra={
                "tag": "lnurluniversal",
                "amount": amount,
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return {"payment_hash": payment_hash, "payment_request": payment_request}

@lnurluniversal_api_router.get("/api/v1/comments/{universal_id}")
async def api_get_comments(
    universal_id: str
) -> list[dict]:
    """Get comments for a universal"""
    universal = await get_lnurluniversal(universal_id)
    if not universal:
        raise HTTPException(status_code=404, detail="Universal not found")

    comments = await get_universal_comments(universal_id)
    return comments

# LNURL-specific routes

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/pay/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
    name="lnurluniversal.api_lnurl_pay",
)
async def api_lnurl_pay(
    request: Request,
    lnurluniversal_id: str,
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        return {"status": "ERROR", "reason": "No lnurluniversal found"}
    return {
        "callback": str(
            request.url_for(
                "lnurluniversal.api_lnurl_pay_callback", lnurluniversal_id=lnurluniversal_id
            )
        ),
        "maxSendable": lnurluniversal.lnurlpayamount * 1000,
        "minSendable": lnurluniversal.lnurlpayamount * 1000,
        "metadata": '[["text/plain", "' + lnurluniversal.name + '"]]',
        "tag": "payRequest",
    }

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/paycb/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
    name="lnurluniversal.api_lnurl_pay_callback",
)
async def api_lnurl_pay_cb(
    request: Request,
    lnurluniversal_id: str,
    amount: int = Query(...),
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    logger.debug(lnurluniversal)
    if not lnurluniversal:
        return {"status": "ERROR", "reason": "No lnurluniversal found"}

    _, payment_request = await create_invoice(
        wallet_id=lnurluniversal.wallet,
        amount=int(amount / 1000),
        memo=lnurluniversal.name,
        unhashed_description=f'[["text/plain", "{lnurluniversal.name}"]]'.encode(),
        extra={
            "tag": "LnurlUniversal",
            "lnurluniversalId": lnurluniversal_id,
            "extra": request.query_params.get("amount"),
        },
    )
    return {
        "pr": payment_request,
        "routes": [],
        "successAction": {"tag": "message", "message": f"Paid {lnurluniversal.name}"},
    }

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/withdraw/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
    name="lnurluniversal.api_lnurl_withdraw",
)
async def api_lnurl_withdraw(
    request: Request,
    lnurluniversal_id: str,
):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        return {"status": "ERROR", "reason": "No lnurluniversal found"}
    k1 = shortuuid.uuid(name=lnurluniversal.id)
    return {
        "tag": "withdrawRequest",
        "callback": str(
            request.url_for(
                "lnurluniversal.api_lnurl_withdraw_callback", lnurluniversal_id=lnurluniversal_id
            )
        ),
        "k1": k1,
        "defaultDescription": lnurluniversal.name,
        "maxWithdrawable": lnurluniversal.lnurlwithdrawamount * 1000,
        "minWithdrawable": lnurluniversal.lnurlwithdrawamount * 1000,
    }

@lnurluniversal_api_router.get(
    "/api/v1/lnurl/withdrawcb/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
    name="lnurluniversal.api_lnurl_withdraw_callback",
)
async def api_lnurl_withdraw_cb(
    lnurluniversal_id: str,
    pr: Optional[str] = None,
    k1: Optional[str] = None,
):
    assert k1, "k1 is required"
    assert pr, "pr is required"
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        return {"status": "ERROR", "reason": "No lnurluniversal found"}

    k1_check = shortuuid.uuid(name=lnurluniversal.id)
    if k1_check != k1:
        return {"status": "ERROR", "reason": "Wrong k1 check provided"}

    await pay_invoice(
        wallet_id=lnurluniversal.wallet,
        payment_request=pr,
        max_sat=int(lnurluniversal.lnurlwithdrawamount * 1000),
        extra={
            "tag": "LnurlUniversal",
            "lnurluniversalId": lnurluniversal_id,
            "lnurlwithdraw": True,
        },
    )
    return {"status": "OK"}
