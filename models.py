# Data models for your extension

from typing import Optional

from pydantic import BaseModel


class CreateLnurlUniversalData(BaseModel):
    name: str
    wallet: Optional[str] = None
    selectedLnurlp: str
    selectedLnurlw: str


class LnurlUniversal(BaseModel):
    id: str
    name: str
    wallet: str
    selectedLnurlp: str
    selectedLnurlw: str
    total_msat: int = 0  # Total balance in msats
    uses: int = 0  # Number of completed transactions
