import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_lnurlFlip, process_payment_with_lock

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    extension_name = "ext_lnurlflip"
    logger.info(f"Starting invoice listener for extension: {extension_name}")
    
    register_invoice_listener(invoice_queue, extension_name)
    logger.info("Invoice listener registered successfully")
    
    while True:
        try:
            payment = await invoice_queue.get()
            logger.info(f"Received payment: {payment.checking_id}")
            if payment.extra and isinstance(payment.extra, dict):
                logger.debug(f"Payment extra data: {payment.extra}")
            
            await on_invoice_paid(payment)
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")


# Do somethhing when an invoice related top this extension is paid

async def on_invoice_paid(payment: Payment) -> None:

    # Get the flip ID
    lnurlflip_id = payment.extra.get("flip_id")
    if not lnurlflip_id:
        logger.warning(f"Payment missing flip_id: {payment}")
        return

    lnurlflip = await get_lnurlFlip(lnurlflip_id)
    if not lnurlflip:
        logger.error(f"Flip not found for id: {lnurlflip_id}")
        return

    # Check if this is a withdrawal
    is_withdrawal = payment.extra.get('lnurlwithdraw', False)
    logger.debug(f"Payment details - withdrawal: {is_withdrawal}, wallet: {payment.wallet_id}, status: {payment.status}")

    # Calculate amount delta based on payment type
    # payment.amount is already in millisatoshis
    amount_msat = abs(payment.amount)
    if is_withdrawal:
        amount_delta = -amount_msat  # Make negative for withdrawals
    else:
        # For incoming payments, amount is positive
        amount_delta = amount_msat

    # Determine if we need to increment uses
    # This happens when a withdrawal brings the balance to exactly 0
    increment_uses = False
    if is_withdrawal:
        current = await get_lnurlFlip(lnurlflip_id)
        if current and current.total_msat + amount_delta == 0:
            increment_uses = True

    # Perform locked payment processing to prevent race conditions
    operation_type = "withdrawal" if is_withdrawal else "payment"
    updated = await process_payment_with_lock(
        lnurlflip_id=lnurlflip_id,
        amount_delta=amount_delta,
        increment_uses=increment_uses,
        operation_type=operation_type
    )

    if updated:
        operation = "withdrawal" if is_withdrawal else "payment"
        logger.info(f"Processed {operation} for flip {lnurlflip_id[:8]}... amount: {abs(amount_delta) // 1000} sats, new balance: {updated.total_msat // 1000} sats")
    else:
        logger.error(f"Failed to update flip {lnurlflip_id}")
