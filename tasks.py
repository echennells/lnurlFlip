import asyncio
import logging

from lnbits.core.models import Payment
from lnbits.core.services import websocket_updater
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_lnurluniversal, update_lnurluniversal

async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    extension_name = get_current_extension_name()
    
    register_invoice_listener(invoice_queue, extension_name)

    while True:
        try:
            payment = await invoice_queue.get()
            await on_invoice_paid(payment)
        except Exception as e:
            print(f"Error processing payment: {str(e)}")

# Do somethhing when an invoice related top this extension is paid

async def on_invoice_paid(payment: Payment) -> None:

    # Get the universal ID
    lnurluniversal_id = payment.extra.get("universal_id")

    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)

    # All payments update the total (positive for incoming, negative for withdrawals)
    current_total = lnurluniversal.total or 0

    # Check if this is a withdrawal
    is_withdrawal = payment.extra.get('lnurlwithdraw', False)

    # Calculate new total based on payment type
    amount = abs(payment.amount)  # Convert to positive first
    if is_withdrawal:
        amount = -amount  # Make negative for withdrawals
    else:
        # For incoming payments, check if the total has already been updated
        if current_total >= amount:
            return

    new_total = current_total + amount

    # Update state based on new total
    if new_total <= 0:
        lnurluniversal.state = "payment"
    else:
        lnurluniversal.state = "withdraw"

    lnurluniversal.total = max(0, new_total)  # Ensure total never goes negative

    await update_lnurluniversal(lnurluniversal)

    # Verify the update worked
    updated = await get_lnurluniversal(lnurluniversal_id)
