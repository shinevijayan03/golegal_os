"""
GoLegal Database Persistence Module
"""
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from domain.models import Base, SysConfig, SysConfigJn

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./golegal.db")

engine = create_engine(
    DEFAULT_DB_URL,
    connect_args={"check_same_thread": False} if DEFAULT_DB_URL.startswith("sqlite") else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(db_engine=None):
    """Create all tables and seed default system configuration if missing."""
    eng = db_engine or engine
    Base.metadata.create_all(bind=eng)

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
                data_pruning_days=27,
                agreement_retain_days=2920,
                stockholding_prepaid_balance=50000.0,
                low_balance_threshold=10000.0
            )
            session.add(config)
            
            jn = SysConfigJn(
                operation="INSERT",
                updated_by_user="SYSTEM_BOOTSTRAP",
                previous_value=None,
                new_value=json.dumps({"stockholding_prepaid_balance": 50000.0, "status": "INITIALIZED"})
            )
            session.add(jn)
            session.commit()
    finally:
        session.close()


def get_db() -> Session:
    """Yield database session for request scope."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
