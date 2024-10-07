import asyncio

from lnbits.core.models import Payment
from lnbits.core.services import websocket_updater
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener

from .crud import get_lnurluniversal, update_lnurluniversal

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


# Do somethhing when an invoice related top this extension is paid


async def on_invoice_paid(payment: Payment) -> None:
    if payment.extra.get("tag") != "LnurlUniversal":
        return

    lnurluniversal_id = payment.extra.get("lnurluniversalId")
    assert lnurluniversal_id, "lnurluniversalId not set in invoice"
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    assert lnurluniversal, "LnurlUniversal does not exist"

    # update something in the db
    if payment.extra.get("lnurlwithdraw"):
        total = lnurluniversal.total - payment.amount
    else:
        total = lnurluniversal.total + payment.amount

    lnurluniversal.total = total
    await update_lnurluniversal(lnurluniversal)

    # here we could send some data to a websocket on
    # wss://<your-lnbits>/api/v1/ws/<lnurluniversal_id> and then listen to it on
    # the frontend, which we do with index.html connectWebocket()

    some_payment_data = {
        "name": lnurluniversal.name,
        "amount": payment.amount,
        "fee": payment.fee,
        "checking_id": payment.checking_id,
    }

    await websocket_updater(lnurluniversal_id, str(some_payment_data))
