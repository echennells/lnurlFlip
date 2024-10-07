# Maybe your extension needs some LNURL stuff.
# Here is a very simple example of how to do it.
# Feel free to delete this file if you don't need it.

from http import HTTPStatus
from typing import Optional

import shortuuid
from fastapi import APIRouter, Query, Request
from lnbits.core.services import create_invoice, pay_invoice
from loguru import logger

from .crud import get_lnurluniversal

#################################################
########### A very simple LNURLpay ##############
# https://github.com/lnurl/luds/blob/luds/06.md #
#################################################
#################################################

lnurluniversal_lnurl_router = APIRouter()


@lnurluniversal_lnurl_router.get(
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


@lnurluniversal_lnurl_router.get(
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


#################################################
######## A very simple LNURLwithdraw ############
# https://github.com/lnurl/luds/blob/luds/03.md #
#################################################
## withdraw is unlimited, look at withdraw ext ##
## for more advanced withdraw options          ##
#################################################


@lnurluniversal_lnurl_router.get(
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


@lnurluniversal_lnurl_router.get(
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
