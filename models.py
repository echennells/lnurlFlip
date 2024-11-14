# Data models for your extension

from typing import Optional

from pydantic import BaseModel


class CreateLnurlUniversalData(BaseModel):
    name: str
    wallet: Optional[str] = None
    lnurlwithdrawamount: Optional[int] = None  # Allow None explicitly
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"

#class LnurlUniversal(BaseModel):
#    id: str
#    wallet: str
#    lnurlpayamount: int
#    name: str
#    lnurlwithdrawamount: int
#    total: int
#    lnurlpay: Optional[str]
#    lnurlwithdraw: Optional[str]


class LnurlUniversal(BaseModel):
    id: str
    name: str
    wallet: str
    lnurlwithdrawamount: Optional[int] = None
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"
    total: int = 0
    uses: int = 0  # Add this line
