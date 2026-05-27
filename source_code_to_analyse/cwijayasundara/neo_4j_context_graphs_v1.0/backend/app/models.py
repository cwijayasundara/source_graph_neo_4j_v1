"""Domain models for Financial Services — auto-generated from ontology."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

class Person(BaseModel):
    """Entity model for Person."""

    name: str = Field(...)
    email: str | None = None
    role: str | None = None
    description: str | None = None

class Organization(BaseModel):
    """Entity model for Organization."""

    name: str = Field(...)
    description: str | None = None
    industry: str | None = None

class Location(BaseModel):
    """Entity model for Location."""

    name: str = Field(...)
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

class Event(BaseModel):
    """Entity model for Event."""

    name: str = Field(...)
    date: datetime | None = None
    description: str | None = None

class Object(BaseModel):
    """Entity model for Object."""

    name: str = Field(...)
    description: str | None = None

class AccountAccountTypeEnum(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    RETIREMENT = "retirement"
    TRUST = "trust"

class AccountStatusEnum(str, Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"

class Account(BaseModel):
    """Entity model for Account."""

    account_id: str = Field(...)
    name: str = Field(...)
    account_type: AccountAccountTypeEnum | None = None
    balance: float | None = None
    currency: str | None = "USD"
    status: AccountStatusEnum | None = None

class TransactionTransactionTypeEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"

class Transaction(BaseModel):
    """Entity model for Transaction."""

    transaction_id: str = Field(...)
    amount: float = Field(...)
    currency: str | None = "USD"
    transaction_type: TransactionTransactionTypeEnum | None = None
    date: datetime = Field(...)
    description: str | None = None

class DecisionDecisionTypeEnum(str, Enum):
    TRADE = "trade"
    RISK_ASSESSMENT = "risk_assessment"
    COMPLIANCE_REVIEW = "compliance_review"
    PORTFOLIO_REBALANCE = "portfolio_rebalance"
    CLIENT_ADVISORY = "client_advisory"

class Decision(BaseModel):
    """Entity model for Decision."""

    decision_id: str = Field(...)
    name: str = Field(...)
    decision_type: DecisionDecisionTypeEnum | None = None
    outcome: str | None = None
    confidence: float | None = None
    date: datetime = Field(...)

class PolicyCategoryEnum(str, Enum):
    COMPLIANCE = "compliance"
    RISK = "risk"
    TRADING = "trading"
    REPORTING = "reporting"
    AML = "aml"

class Policy(BaseModel):
    """Entity model for Policy."""

    policy_id: str = Field(...)
    name: str = Field(...)
    category: PolicyCategoryEnum | None = None
    description: str | None = None
    effective_date: date | None = None

class SecuritySecurityTypeEnum(str, Enum):
    EQUITY = "equity"
    BOND = "bond"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    OPTION = "option"
    FUTURES = "futures"

class Security(BaseModel):
    """Entity model for Security."""

    ticker: str = Field(...)
    name: str = Field(...)
    security_type: SecuritySecurityTypeEnum | None = None
    sector: str | None = None

