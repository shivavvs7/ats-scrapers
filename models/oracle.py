from pydantic import BaseModel
from typing import List, Optional, Any


class OracleLocation(BaseModel):
    """Location data from Oracle HCM Cloud API"""
    Id: Optional[int] = None
    City: Optional[str] = None
    Country: Optional[str] = None
    LocationName: Optional[str] = None
    AddressLine1: Optional[str] = None
    State: Optional[str] = None
    PostalCode: Optional[str] = None


class OracleRequisitionFlexField(BaseModel):
    """Custom company fields from Oracle HCM Cloud API"""
    Id: Optional[int] = None
    Name: Optional[str] = None
    Value: Optional[str] = None
    DisplayValue: Optional[str] = None


class OracleJob(BaseModel):
    """Main job model for Oracle HCM Cloud (Oracle Recruiting Cloud)"""

    # Identifiers
    Id: Optional[int] = None
    JobId: Optional[str] = None
    RequisitionNumber: Optional[str] = None

    # Basic Details
    Title: Optional[str] = None
    ShortDescriptionStr: Optional[str] = None
    ExternalDescriptionInt: Optional[str] = None

    # Location
    PrimaryLocation: Optional[str] = None
    Country: Optional[str] = None
    WorkLocation: Optional[OracleLocation] = None
    otherWorkLocations: Optional[List[OracleLocation]] = None
    secondaryLocations: Optional[List[Any]] = None

    # Dates
    PostedDate: Optional[str] = None
    ClosingDate: Optional[str] = None

    # Categorization
    OrganizationName: Optional[str] = None
    JobCategoryName: Optional[str] = None
    JobFamilyName: Optional[str] = None

    # Employment Type
    FullOrPartTime: Optional[str] = None
    FlexibleJobOption: Optional[str] = None  # Remote/Hybrid/Onsite

    # URLs
    JobURL: Optional[str] = None
    ExternalApplyURL: Optional[str] = None

    # Custom Fields
    requisitionFlexFields: Optional[List[OracleRequisitionFlexField]] = None

    # Additional Fields
    HiringManagerName: Optional[str] = None
    RecruiterName: Optional[str] = None
    MinimumSalary: Optional[int] = None
    MaximumSalary: Optional[int] = None
    CurrencyCode: Optional[str] = None
