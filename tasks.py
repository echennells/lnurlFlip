import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_lnurluniversal, process_payment_with_lock
from .utils import sats_to_msats

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    extension_name = "ext_lnurluniversal"
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
    logger.info(f"Payment amount: {payment.amount} sats ({sats_to_msats(payment.amount)} msats)")
    logger.info(f"Payment tag: {payment.extra.get('tag') if payment.extra else 'No tag'}")
    logger.info(f"Payment hash: {payment.payment_hash}")

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
    # payment.amount is in satoshis, convert to millisatoshis
    amount_msat = sats_to_msats(abs(payment.amount))  # Convert sats to msats
    if is_withdrawal:
        amount_delta = -amount_msat  # Make negative for withdrawals
        logger.info(f"This is a withdrawal. Amount delta: {amount_delta} msats")
    else:
        # For incoming payments, amount is positive
        amount_delta = amount_msat
        logger.info(f"This is an incoming payment. Amount delta: {amount_delta} msats")
        
        # Check if the total has already been updated for incoming payments
        # This prevents double-processing
        current = await get_lnurluniversal(lnurluniversal_id)
        if current and current.total_msat >= amount_msat:
            logger.info(f"Total already updated. Current total: {current.total_msat} msats, Amount: {amount_msat} msats")
            return

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
        logger.info(f"After atomic update - total: {updated.total_msat}, state: {updated.state}, uses: {getattr(updated, 'uses', 0)}")
    else:
        logger.error(f"Failed to update universal {lnurluniversal_id}")
    logger.info("-------- PAYMENT PROCESSING END --------")
