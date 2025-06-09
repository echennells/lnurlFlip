import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_lnurluniversal, process_payment_with_lock
from .utils import sats_to_msats, msats_to_sats

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    extension_name = "ext_lnurluniversal"
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
    logger.info(f"Processing payment {payment.payment_hash[:8]}... amount: {msats_to_sats(payment.amount)} sats")

    # Get the universal ID
    lnurluniversal_id = payment.extra.get("universal_id")
    if not lnurluniversal_id:
        logger.warning(f"Payment missing universal_id: {payment}")
        return

    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        logger.error(f"Universal not found for id: {lnurluniversal_id}")
        return

    # Check if this is a withdrawal
    is_withdrawal = payment.extra.get('lnurlwithdraw', False)
    logger.info(f"Is withdrawal: {is_withdrawal}")
    logger.info(f"Payment wallet_id: {payment.wallet_id}")
    logger.info(f"Payment status: {payment.status}")
    logger.info(f"Payment pending: {payment.pending}")

    # Calculate amount delta based on payment type
    # payment.amount is already in millisatoshis
    amount_msat = abs(payment.amount)
    if is_withdrawal:
        amount_delta = -amount_msat  # Make negative for withdrawals
        logger.info(f"This is a withdrawal. Amount delta: {amount_delta} msats")
    else:
        # For incoming payments, amount is positive
        amount_delta = amount_msat
        logger.info(f"This is an incoming payment. Amount delta: {amount_delta} msats")

    # Determine if we need to increment uses
    # This happens when a withdrawal brings the balance to exactly 0
    increment_uses = False
    if is_withdrawal:
        current = await get_lnurluniversal(lnurluniversal_id)
        if current and current.total_msat + amount_delta == 0:
            increment_uses = True
            logger.info("This withdrawal will bring balance to 0, incrementing uses")

    # Perform locked payment processing to prevent race conditions
    operation_type = "withdrawal" if is_withdrawal else "payment"
    updated = await process_payment_with_lock(
        lnurluniversal_id=lnurluniversal_id,
        amount_delta=amount_delta,
        increment_uses=increment_uses,
        operation_type=operation_type
    )

    if updated:
        logger.info(f"After atomic update - total: {updated.total_msat}, uses: {getattr(updated, 'uses', 0)}")
    else:
        logger.error(f"Failed to update universal {lnurluniversal_id}")
    
    logger.info(f"Payment {payment.payment_hash[:8]}... processed successfully")
