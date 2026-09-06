"""
GoLegal Database Persistence Module

Engine + session factory, schema bootstrap, lightweight additive migrations for
SQLite (so an existing golegal.db keeps working after new columns are added),
and demo-account seeding.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from domain.models import Base, SysConfig, SysConfigJn, User

DEFAULT_DB_URL = settings.database_url

engine = create_engine(
    DEFAULT_DB_URL,
    connect_args={"check_same_thread": False} if DEFAULT_DB_URL.startswith("sqlite") else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _apply_additive_migrations(eng) -> None:
    """Add columns introduced after the initial schema. SQLite cannot ALTER
    constraints, so this only covers `ADD COLUMN`; anything else needs a fresh DB."""
    inspector = inspect(eng)
    existing_tables = set(inspector.get_table_names())
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(dialect=eng.dialect)
                default_sql = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    val = column.default.arg
                    if isinstance(val, bool):
                        default_sql = f" DEFAULT {1 if val else 0}"
                    elif isinstance(val, (int, float)):
                        default_sql = f" DEFAULT {val}"
                    elif isinstance(val, str):
                        default_sql = f" DEFAULT '{val}'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}'))


def seed_demo_accounts(session: Session) -> None:
    """Create the persona accounts from the PRD when they do not exist."""
    from security.auth import AuthService  # local import avoids a circular dependency

    for acct in settings.demo_accounts:
        if session.query(User).filter_by(email=acct["email"]).first():
            continue
        user = User(
            id=acct["id"],
            user_type=acct["user_type"],
            full_name=acct["full_name"],
            email=acct["email"],
            phone=acct["phone"],
            address=acct.get("address"),
            state_code="KA",
            password_hash=AuthService.hash_password("GoLegal@123"),
        )
        session.add(user)
    session.commit()


def init_db(db_engine=None, seed_demo: bool = True):
    """Create all tables, apply additive migrations, and seed configuration."""
    eng = db_engine or engine
    Base.metadata.create_all(bind=eng)
    _apply_additive_migrations(eng)

    session = sessionmaker(bind=eng)()
    try:
        config = session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        if not config:
            config = SysConfig(
                id="GLOBAL_CONFIG",
                lang="en",
                dig_sign="Aadhaar_eSign",
                estamp=True,
                estamp_vendor="StockHolding",
                currency="INR",
                system_commission=18.0,
                discount=0.0,
                country="IND",
                data_pruning_days=settings.draft_pruning_days,
                agreement_retain_days=settings.agreement_retain_days,
                stockholding_prepaid_balance=settings.initial_prepaid_balance,
                low_balance_threshold=settings.low_balance_threshold,
            )
            session.add(config)
            session.add(SysConfigJn(
                operation="INSERT",
                updated_by_user="SYSTEM_BOOTSTRAP",
                previous_value=None,
                new_value=json.dumps({"stockholding_prepaid_balance": settings.initial_prepaid_balance,
                                      "status": "INITIALIZED"}),
            ))
            session.commit()
        if seed_demo:
            seed_demo_accounts(session)
    finally:
        session.close()


@contextmanager
def session_scope():
    """Transactional scope: commits on success, rolls back on error, always closes."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Session:
    """Yield database session for request scope."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
