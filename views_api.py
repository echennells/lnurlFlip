from http import HTTPStatus

from fastapi import APIRouter, Depends, Query, Request
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import (
    get_key_type,
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash
from lnurl import encode as lnurl_encode
from starlette.exceptions import HTTPException

from .crud import (
    create_lnurluniversal,
    delete_lnurluniversal,
    get_lnurluniversal,
    get_lnurluniversals,
    update_lnurluniversal,
)
from .models import CreateLnurlUniversalData, LnurlUniversal

lnurluniversal_api_router = APIRouter()


#######################################
##### ADD YOUR API ENDPOINTS HERE #####
#######################################

## Get all the records belonging to the user


@lnurluniversal_api_router.get("/api/v1/myex", status_code=HTTPStatus.OK)
async def api_lnurluniversals(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(get_key_type),
):
    wallet_ids = [wallet.wallet.id]
    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []
    return [lnurluniversal.dict() for lnurluniversal in await get_lnurluniversals(wallet_ids)]


## Get a single record


@lnurluniversal_api_router.get(
    "/api/v1/myex/{lnurluniversal_id}",
    status_code=HTTPStatus.OK,
    dependencies=[Depends(require_invoice_key)],
)
async def api_lnurluniversal(lnurluniversal_id: str):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )
    return lnurluniversal.dict()


## update a record


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

    for key, value in data.dict().items():
        setattr(lnurluniversal, key, value)

    return await update_lnurluniversal(lnurluniversal)


## Create a new record


@lnurluniversal_api_router.post("/api/v1/myex", status_code=HTTPStatus.CREATED)
async def api_lnurluniversal_create(
    request: Request,
    data: CreateLnurlUniversalData,
    key_type: WalletTypeInfo = Depends(require_admin_key),
) -> LnurlUniversal:
    lnurluniversal_id = urlsafe_short_hash()
    lnurlpay = lnurl_encode(
        str(request.url_for("lnurluniversal.api_lnurl_pay", lnurluniversal_id=lnurluniversal_id))
    )
    lnurlwithdraw = lnurl_encode(
        str(
            request.url_for(
                "lnurluniversal.api_lnurl_withdraw", lnurluniversal_id=lnurluniversal_id
            )
        )
    )
    data.wallet = data.wallet or key_type.wallet.id
    myext = LnurlUniversal(
        id=lnurluniversal_id,
        lnurlpay=lnurlpay,
        lnurlwithdraw=lnurlwithdraw,
        **data.dict(),
    )
    return await create_lnurluniversal(myext)


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
