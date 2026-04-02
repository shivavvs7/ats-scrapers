from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JoinCity(BaseModel):
    id: Optional[str] = None
    countryCode: Optional[str] = None
    cityName: Optional[str] = None
    regionName: Optional[str] = None
    countryName: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    defaultZipCode: Optional[str] = None
    googlePlaceId: Optional[str] = None


class JoinCountry(BaseModel):
    id: Optional[int] = None
    iso3166: Optional[str] = None
    name: Optional[str] = None


class JoinCategory(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


class JoinEmploymentType(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


class JoinOffice(BaseModel):
    id: Optional[int] = None
    countryId: Optional[int] = None
    cityId: Optional[str] = None


class JoinSettings(BaseModel):
    showSalary: Optional[bool] = None


class JoinJob(BaseModel):
    id: int
    idParam: Optional[str] = None
    title: str
    createdAt: Optional[datetime] = None
    employmentTypeId: Optional[int] = None
    salaryFrequency: Optional[str] = None
    categoryId: Optional[int] = None
    countryId: Optional[int] = None
    cityId: Optional[str] = None
    companyId: Optional[int] = None
    languageId: Optional[int] = None
    workplaceType: Optional[str] = None
    settings: Optional[JoinSettings] = None
    office: Optional[JoinOffice] = None
    category: Optional[JoinCategory] = None
    employmentType: Optional[JoinEmploymentType] = None
    country: Optional[JoinCountry] = None
    city: Optional[JoinCity] = None

    @property
    def location(self) -> str:
        """Build location string from city and country."""
        parts = []
        if self.city and self.city.cityName:
            parts.append(self.city.cityName)
        if self.country and self.country.name:
            parts.append(self.country.name)
        return ", ".join(parts) if parts else ""


class JoinCompanyData(BaseModel):
    """Wrapper for stored company data with metadata."""

    jobs: List[JoinJob] = Field(default_factory=list)
    name: Optional[str] = None
    last_scraped: Optional[str] = None
