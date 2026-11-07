"""Plain data records. All behaviour lives in system.py."""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    year: int
    copies: int = 1
    available: int = 1
    times_borrowed: int = 0


@dataclass
class Member:
    member_id: str
    name: str
    active: Dict[str, int] = field(default_factory=dict)   # isbn -> loan_id of open loans
    history: List[int] = field(default_factory=list)       # every loan_id, oldest first
    borrowed: Set[str] = field(default_factory=set)        # every isbn ever borrowed
    fines_owed: int = 0


@dataclass
class Loan:
    loan_id: int
    isbn: str
    member_id: str
    issued: date
    due: date
    returned_on: Optional[date] = None
    renewals: int = 0
    fine: int = 0
    # Bookkeeping that lets an issue be undone exactly (not saved to disk):
    first_time: bool = False                       # first time this member borrowed this title?
    links: List[str] = field(default_factory=list)  # recommendation-graph edges this loan added
