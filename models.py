# Data models for your extension

from typing import Optional

from pydantic import BaseModel


class CreateLnurlUniversalData(BaseModel):
    name: str
    wallet: Optional[str] = None
    lnurlwithdrawamount_sat: Optional[int] = None  # Amount in sats (if set)
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"


class LnurlUniversal(BaseModel):
    id: str
    name: str
    wallet: str
    lnurlwithdrawamount_sat: Optional[int] = None  # Amount in sats (if set)
    selectedLnurlp: str
    selectedLnurlw: str
    state: str = "payment"
    total_msat: int = 0  # Total balance in msats
    uses: int = 0  # Number of completed transactions
