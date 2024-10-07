# Data models for your extension

from typing import Optional

from pydantic import BaseModel


class CreateLnurlUniversalData(BaseModel):
    name: str
    lnurlpayamount: int
    lnurlwithdrawamount: int
    wallet: Optional[str] = None
    total: int = 0


class LnurlUniversal(BaseModel):
    id: str
    wallet: str
    lnurlpayamount: int
    name: str
    lnurlwithdrawamount: int
    total: int
    lnurlpay: Optional[str]
    lnurlwithdraw: Optional[str]
