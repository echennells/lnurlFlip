import asyncio
import logging

from lnbits.core.models import Payment
from lnbits.core.services import websocket_updater
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_lnurluniversal, update_lnurluniversal

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    extension_name = get_current_extension_name()
    logger.warning(f"Starting invoice listener for extension: {extension_name}")  # Changed to warning for visibility
    
    register_invoice_listener(invoice_queue, extension_name)
    logger.warning("Invoice listener registered successfully")
    
    while True:
        try:
            logger.warning("Waiting for next payment...")
            payment = await invoice_queue.get()
            logger.warning(f"Received payment: {payment.checking_id}")
            logger.warning(f"Payment extra data: {payment.extra}")
            if payment.extra and isinstance(payment.extra, dict):
                logger.warning(f"Payment tag: {payment.extra.get('tag')}")
            await on_invoice_paid(payment)
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")


# Do somethhing when an invoice related top this extension is paid

async def on_invoice_paid(payment: Payment) -> None:
    logger.info("-------- PAYMENT PROCESSING START --------")
    logger.info(f"Processing payment in on_invoice_paid: {payment}")
    logger.info(f"Payment extra data: {payment.extra}")
    logger.info(f"Payment amount: {payment.amount}")

    # Get the universal ID
    lnurluniversal_id = payment.extra.get("universal_id")
    if not lnurluniversal_id:
        logger.warning(f"Payment missing universal_id: {payment}")
        return

    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error(f"Universal not found for id: {lnurluniversal_id}")
        return

    # All payments update the total (positive for incoming, negative for withdrawals)
    current_total = lnurluniversal.total or 0
    logger.info(f"Current total before update: {current_total}")
    logger.info(f"Current uses value: {getattr(lnurluniversal, 'uses', 0)}")

    # Check if this is a withdrawal
    is_withdrawal = payment.extra.get('lnurlwithdraw', False)
    logger.info(f"Is withdrawal: {is_withdrawal}")

    # Calculate new total based on payment type
    amount = abs(payment.amount)  # Convert to positive first
    if is_withdrawal:
        amount = -amount  # Make negative for withdrawals
        logger.info(f"This is a withdrawal. Current total: {current_total}, Amount: {amount}")
        # Check if this withdrawal will complete a use cycle
        if current_total + amount <= 0:
            logger.info("This withdrawal will bring balance to 0 or below")
            current_uses = getattr(lnurluniversal, 'uses', 0)
            lnurluniversal.uses = current_uses + 1
            logger.info(f"Incrementing uses from {current_uses} to {lnurluniversal.uses}")

    new_total = current_total + amount
    logger.info(f"Amount being applied: {amount}")
    logger.info(f"New total after calculation: {new_total}")

    # Update state based on new total
    if new_total <= 0:
        lnurluniversal.state = "payment"
        logger.info("Setting state to payment")
    else:
        lnurluniversal.state = "withdraw"
        logger.info("Setting state to withdraw")

    lnurluniversal.total = max(0, new_total)  # Ensure total never goes negative
    logger.info(f"Final values before update - total: {lnurluniversal.total}, state: {lnurluniversal.state}, uses: {getattr(lnurluniversal, 'uses', 0)}")

    await update_lnurluniversal(lnurluniversal)

    # Verify the update worked
    updated = await get_lnurluniversal(lnurluniversal_id)
    logger.info(f"After update verification - total: {updated.total}, state: {updated.state}, uses: {getattr(updated, 'uses', 0)}")
    logger.info("-------- PAYMENT PROCESSING END --------")
