# Data models for your extension

from typing import Optional

from pydantic import BaseModel


class CreateLnurlUniversalData(BaseModel):
    name: str
    wallet: Optional[str] = None
    lnurlwithdrawamount: Optional[int] = None  # Amount in sats (if set)
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"


class LnurlUniversal(BaseModel):
    id: str
    name: str
    wallet: str
    lnurlwithdrawamount: Optional[int] = None  # Amount in sats (if set)
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"
    total: int = 0  # Total balance in msats
    uses: int = 0  # Number of completed transactions
