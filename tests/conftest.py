"""
Pytest Fixtures for GoLegal Automated Test Suite
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from domain.models import Base, User, Agreement, Party, SysConfig, SysConfigJn
from services.stamping_service import StampingService
from services.esign_service import ESignService
from services.workflow_service import WorkflowService
from security.cbac import CBACService


@pytest.fixture
def db_session():
    """In-memory SQLite database session isolated per test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed default sysconfig
    config = SysConfig(
        id="GLOBAL_CONFIG",
        lang="en",
        dig_sign="Aadhaar_eSign",
        estamp=True,
        estamp_vendor="StockHolding",
        currency="INR",
        stockholding_prepaid_balance=50000.0,
        low_balance_threshold=10000.0
    )
    session.add(config)
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_users(db_session):
    """Seed test users (Owner, Tenant, Witness)."""
    owner = User(
        id="usr-owner-001",
        user_type="Single_User",
        full_name="Ramakiran Reddy",
        email="ramakiran.reddy@example.com",
        phone="9876543210",
        address="101, Palm Meadows, Bangalore"
    )
    tenant = User(
        id="usr-tenant-001",
        user_type="Single_User",
        full_name="Mayank Tripathi",
        email="mayank.tripathi@example.com",
        phone="9876543211",
        address="Flat 202, Green Glen, Bangalore"
    )
    db_session.add_all([owner, tenant])
    db_session.commit()
    return {"owner": owner, "tenant": tenant}


@pytest.fixture
def sample_agreement(db_session, sample_users):
    """Create a sample residential rental agreement with 1 Owner, 1 Tenant, 1 Witness."""
    agr = Agreement(
        id="agr-test-001",
        initiator_id=sample_users["owner"].id,
        agreement_type="Rental_Residential",
        state_code="KA",
        status="Draft",
        cloud_storage_consent=True
    )
    agr.set_property_details({
        "premises_name": "Sunrise Apartments #402",
        "address_line1": "Outer Ring Road, Bellandur",
        "city": "Bangalore",
        "state": "KA",
        "pincode": "560103",
        "property_type": "Apartment"
    })
    agr.set_commercial_terms({
        "monthly_rent": 28000.0,
        "security_deposit": 120000.0,
        "lease_period_months": 11,
        "rent_commencement_date": "2026-10-01",
        "rent_due_day": 5
    })
    db_session.add(agr)
    db_session.commit()

    owner_party = Party(
        id="pty-owner-001",
        agreement_id=agr.id,
        party_type="Owner",
        full_name="Ramakiran Reddy",
        email="ramakiran.reddy@example.com",
        phone="9876543210",
        aadhaar_masked="XXXXXXXX1111",
        signing_status="Pending"
    )
    tenant_party = Party(
        id="pty-tenant-001",
        agreement_id=agr.id,
        party_type="Tenant",
        full_name="Mayank Tripathi",
        email="mayank.tripathi@example.com",
        phone="9876543211",
        aadhaar_masked="XXXXXXXX2222",
        signing_status="Pending"
    )
    witness_party = Party(
        id="pty-witness-001",
        agreement_id=agr.id,
        party_type="Witness",
        full_name="Suresh Kumar",
        email="suresh.kumar@example.com",
        phone="9876543212",
        aadhaar_masked="XXXXXXXX3333",
        signing_status="Pending"
    )
    db_session.add_all([owner_party, tenant_party, witness_party])
    db_session.commit()

    return agr


@pytest.fixture
def stamping_svc(db_session):
    return StampingService(db_session)


@pytest.fixture
def esign_svc(db_session):
    return ESignService(db_session)


@pytest.fixture
def workflow_svc(db_session):
    return WorkflowService(db_session)


@pytest.fixture
def cbac_svc():
    return CBACService(secret_key="test_secret_key_123")
