"""Shared test fixtures."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test database before importing models
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from quote_manager.models.base import Base
from quote_manager.models import Project, Supplier, Quote, LineItem


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_project(db_session):
    """Create a sample project."""
    project = Project(name="テスト案件", gmail_query="subject:見積テスト")
    db_session.add(project)
    db_session.commit()
    return project


@pytest.fixture
def sample_suppliers(db_session):
    """Create sample suppliers."""
    suppliers = [
        Supplier(name="A社", email="a@example.com"),
        Supplier(name="B社", email="b@example.com"),
        Supplier(name="C社", email="c@example.com"),
    ]
    db_session.add_all(suppliers)
    db_session.commit()
    return suppliers
