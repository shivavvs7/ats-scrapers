#!/usr/bin/env python3
"""
Personio Company Discovery Script

This script uses SearXNG to discover companies using Personio for job postings.
It searches using multiple strategies to maximize discovery:
- Industry keywords
- Location/country keywords
- Job role keywords
- Technology keywords
- Company name patterns
- Pagination for deeper results

Usage:
    python discover_companies.py [--searxng-url URL] [--output FILE] [--delay SECONDS]
"""

import argparse
import csv
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Set
import urllib.request
import urllib.error


@dataclass
class Company:
    name: str
    url: str
    subdomain: str


# Massive search query list for maximum discovery
SEARCH_QUERIES = [
    # Direct site searches with variations
    "site:jobs.personio.com",
    "site:jobs.personio.de",
    "site:jobs.personio.ch",
    "site:jobs.personio.at",
    "site:jobs.personio.fr",
    "site:jobs.personio.it",
    "site:jobs.personio.es",
    "site:jobs.personio.pt",
    "site:jobs.personio.nl",
    "site:*.site:jobs.personio.com",
    '"site:jobs.personio.com"',
    "inurl:jobs.personio.com",
    # German company suffixes (most Personio customers)
    "site:jobs.personio.com GmbH",
    "site:jobs.personio.com AG",
    "site:jobs.personio.com SE",
    "site:jobs.personio.com KG",
    "site:jobs.personio.com OHG",
    "site:jobs.personio.com UG",
    "site:jobs.personio.com e.V.",
    "site:jobs.personio.com mbH",
    "site:jobs.personio.com GmbH & Co",
    # Other European company suffixes
    "site:jobs.personio.com BV",
    "site:jobs.personio.com NV",
    "site:jobs.personio.com Ltd",
    "site:jobs.personio.com Limited",
    "site:jobs.personio.com PLC",
    "site:jobs.personio.com Inc",
    "site:jobs.personio.com Corp",
    "site:jobs.personio.com SA",
    "site:jobs.personio.com SAS",
    "site:jobs.personio.com SARL",
    "site:jobs.personio.com SL",
    "site:jobs.personio.com Srl",
    "site:jobs.personio.com SpA",
    "site:jobs.personio.com AB",
    "site:jobs.personio.com ApS",
    "site:jobs.personio.com AS",
    "site:jobs.personio.com Oy",
    # Industries - Extensive
    "site:jobs.personio.com software",
    "site:jobs.personio.com tech",
    "site:jobs.personio.com technology",
    "site:jobs.personio.com IT",
    "site:jobs.personio.com digital",
    "site:jobs.personio.com internet",
    "site:jobs.personio.com fintech",
    "site:jobs.personio.com finance",
    "site:jobs.personio.com banking",
    "site:jobs.personio.com investment",
    "site:jobs.personio.com trading",
    "site:jobs.personio.com payments",
    "site:jobs.personio.com healthcare",
    "site:jobs.personio.com health",
    "site:jobs.personio.com medical",
    "site:jobs.personio.com hospital",
    "site:jobs.personio.com clinic",
    "site:jobs.personio.com biotech",
    "site:jobs.personio.com pharma",
    "site:jobs.personio.com pharmaceutical",
    "site:jobs.personio.com life sciences",
    "site:jobs.personio.com diagnostics",
    "site:jobs.personio.com automotive",
    "site:jobs.personio.com mobility",
    "site:jobs.personio.com car",
    "site:jobs.personio.com vehicle",
    "site:jobs.personio.com manufacturing",
    "site:jobs.personio.com industrial",
    "site:jobs.personio.com production",
    "site:jobs.personio.com machinery",
    "site:jobs.personio.com engineering",
    "site:jobs.personio.com logistics",
    "site:jobs.personio.com supply chain",
    "site:jobs.personio.com shipping",
    "site:jobs.personio.com freight",
    "site:jobs.personio.com warehouse",
    "site:jobs.personio.com ecommerce",
    "site:jobs.personio.com e-commerce",
    "site:jobs.personio.com retail",
    "site:jobs.personio.com shopping",
    "site:jobs.personio.com marketplace",
    "site:jobs.personio.com fashion",
    "site:jobs.personio.com apparel",
    "site:jobs.personio.com clothing",
    "site:jobs.personio.com luxury",
    "site:jobs.personio.com food",
    "site:jobs.personio.com beverage",
    "site:jobs.personio.com restaurant",
    "site:jobs.personio.com catering",
    "site:jobs.personio.com hospitality",
    "site:jobs.personio.com hotel",
    "site:jobs.personio.com travel",
    "site:jobs.personio.com tourism",
    "site:jobs.personio.com airline",
    "site:jobs.personio.com education",
    "site:jobs.personio.com training",
    "site:jobs.personio.com university",
    "site:jobs.personio.com school",
    "site:jobs.personio.com learning",
    "site:jobs.personio.com academy",
    "site:jobs.personio.com consulting",
    "site:jobs.personio.com advisory",
    "site:jobs.personio.com management consulting",
    "site:jobs.personio.com strategy",
    "site:jobs.personio.com legal",
    "site:jobs.personio.com law firm",
    "site:jobs.personio.com lawyer",
    "site:jobs.personio.com insurance",
    "site:jobs.personio.com insurtech",
    "site:jobs.personio.com real estate",
    "site:jobs.personio.com property",
    "site:jobs.personio.com immobilien",
    "site:jobs.personio.com construction",
    "site:jobs.personio.com building",
    "site:jobs.personio.com architecture",
    "site:jobs.personio.com energy",
    "site:jobs.personio.com power",
    "site:jobs.personio.com utilities",
    "site:jobs.personio.com renewable",
    "site:jobs.personio.com solar",
    "site:jobs.personio.com wind",
    "site:jobs.personio.com battery",
    "site:jobs.personio.com sustainability",
    "site:jobs.personio.com climate",
    "site:jobs.personio.com cleantech",
    "site:jobs.personio.com green",
    "site:jobs.personio.com environmental",
    "site:jobs.personio.com gaming",
    "site:jobs.personio.com games",
    "site:jobs.personio.com esports",
    "site:jobs.personio.com entertainment",
    "site:jobs.personio.com media",
    "site:jobs.personio.com publishing",
    "site:jobs.personio.com news",
    "site:jobs.personio.com broadcasting",
    "site:jobs.personio.com streaming",
    "site:jobs.personio.com music",
    "site:jobs.personio.com video",
    "site:jobs.personio.com film",
    "site:jobs.personio.com advertising",
    "site:jobs.personio.com marketing",
    "site:jobs.personio.com agency",
    "site:jobs.personio.com creative",
    "site:jobs.personio.com design",
    "site:jobs.personio.com branding",
    "site:jobs.personio.com PR",
    "site:jobs.personio.com telecom",
    "site:jobs.personio.com telecommunications",
    "site:jobs.personio.com network",
    "site:jobs.personio.com security",
    "site:jobs.personio.com cybersecurity",
    "site:jobs.personio.com infosec",
    "site:jobs.personio.com aerospace",
    "site:jobs.personio.com aviation",
    "site:jobs.personio.com defense",
    "site:jobs.personio.com space",
    "site:jobs.personio.com satellite",
    "site:jobs.personio.com sports",
    "site:jobs.personio.com fitness",
    "site:jobs.personio.com gym",
    "site:jobs.personio.com wellness",
    "site:jobs.personio.com beauty",
    "site:jobs.personio.com cosmetics",
    "site:jobs.personio.com skincare",
    "site:jobs.personio.com personal care",
    "site:jobs.personio.com agriculture",
    "site:jobs.personio.com agritech",
    "site:jobs.personio.com farming",
    "site:jobs.personio.com proptech",
    "site:jobs.personio.com regtech",
    "site:jobs.personio.com legaltech",
    "site:jobs.personio.com edtech",
    "site:jobs.personio.com healthtech",
    "site:jobs.personio.com medtech",
    "site:jobs.personio.com hrtech",
    "site:jobs.personio.com martech",
    "site:jobs.personio.com adtech",
    "site:jobs.personio.com robotics",
    "site:jobs.personio.com automation",
    "site:jobs.personio.com IoT",
    "site:jobs.personio.com embedded",
    "site:jobs.personio.com hardware",
    "site:jobs.personio.com electronics",
    "site:jobs.personio.com semiconductor",
    "site:jobs.personio.com blockchain",
    "site:jobs.personio.com crypto",
    "site:jobs.personio.com cryptocurrency",
    "site:jobs.personio.com web3",
    "site:jobs.personio.com DeFi",
    "site:jobs.personio.com NFT",
    "site:jobs.personio.com AI",
    "site:jobs.personio.com artificial intelligence",
    "site:jobs.personio.com machine learning",
    "site:jobs.personio.com ML",
    "site:jobs.personio.com deep learning",
    "site:jobs.personio.com NLP",
    "site:jobs.personio.com computer vision",
    "site:jobs.personio.com data",
    "site:jobs.personio.com analytics",
    "site:jobs.personio.com big data",
    "site:jobs.personio.com business intelligence",
    "site:jobs.personio.com cloud",
    "site:jobs.personio.com SaaS",
    "site:jobs.personio.com PaaS",
    "site:jobs.personio.com IaaS",
    "site:jobs.personio.com B2B",
    "site:jobs.personio.com B2C",
    "site:jobs.personio.com D2C",
    "site:jobs.personio.com platform",
    "site:jobs.personio.com startup",
    "site:jobs.personio.com scaleup",
    "site:jobs.personio.com venture",
    "site:jobs.personio.com nonprofit",
    "site:jobs.personio.com NGO",
    "site:jobs.personio.com foundation",
    "site:jobs.personio.com charity",
    "site:jobs.personio.com research",
    "site:jobs.personio.com laboratory",
    "site:jobs.personio.com institute",
    "site:jobs.personio.com chemicals",
    "site:jobs.personio.com materials",
    "site:jobs.personio.com plastics",
    "site:jobs.personio.com packaging",
    "site:jobs.personio.com printing",
    "site:jobs.personio.com textiles",
    "site:jobs.personio.com furniture",
    "site:jobs.personio.com consumer goods",
    "site:jobs.personio.com FMCG",
    "site:jobs.personio.com pet",
    "site:jobs.personio.com veterinary",
    "site:jobs.personio.com dental",
    "site:jobs.personio.com optical",
    "site:jobs.personio.com hearing",
    # Countries - Comprehensive
    "site:jobs.personio.com Germany",
    "site:jobs.personio.com Deutschland",
    "site:jobs.personio.com Austria",
    "site:jobs.personio.com Österreich",
    "site:jobs.personio.com Switzerland",
    "site:jobs.personio.com Schweiz",
    "site:jobs.personio.com Netherlands",
    "site:jobs.personio.com Holland",
    "site:jobs.personio.com Belgium",
    "site:jobs.personio.com Belgien",
    "site:jobs.personio.com France",
    "site:jobs.personio.com Frankreich",
    "site:jobs.personio.com Spain",
    "site:jobs.personio.com Spanien",
    "site:jobs.personio.com Portugal",
    "site:jobs.personio.com Italy",
    "site:jobs.personio.com Italien",
    "site:jobs.personio.com UK",
    "site:jobs.personio.com United Kingdom",
    "site:jobs.personio.com Britain",
    "site:jobs.personio.com England",
    "site:jobs.personio.com Scotland",
    "site:jobs.personio.com Wales",
    "site:jobs.personio.com Ireland",
    "site:jobs.personio.com Irland",
    "site:jobs.personio.com Poland",
    "site:jobs.personio.com Polen",
    "site:jobs.personio.com Czech Republic",
    "site:jobs.personio.com Czechia",
    "site:jobs.personio.com Sweden",
    "site:jobs.personio.com Schweden",
    "site:jobs.personio.com Norway",
    "site:jobs.personio.com Norwegen",
    "site:jobs.personio.com Denmark",
    "site:jobs.personio.com Dänemark",
    "site:jobs.personio.com Finland",
    "site:jobs.personio.com Finnland",
    "site:jobs.personio.com Luxembourg",
    "site:jobs.personio.com Luxemburg",
    "site:jobs.personio.com Hungary",
    "site:jobs.personio.com Ungarn",
    "site:jobs.personio.com Romania",
    "site:jobs.personio.com Rumänien",
    "site:jobs.personio.com Greece",
    "site:jobs.personio.com Griechenland",
    "site:jobs.personio.com Croatia",
    "site:jobs.personio.com Kroatien",
    "site:jobs.personio.com Slovenia",
    "site:jobs.personio.com Slowenien",
    "site:jobs.personio.com Slovakia",
    "site:jobs.personio.com Slowakei",
    "site:jobs.personio.com Estonia",
    "site:jobs.personio.com Estland",
    "site:jobs.personio.com Latvia",
    "site:jobs.personio.com Lettland",
    "site:jobs.personio.com Lithuania",
    "site:jobs.personio.com Litauen",
    "site:jobs.personio.com Bulgaria",
    "site:jobs.personio.com Bulgarien",
    "site:jobs.personio.com Serbia",
    "site:jobs.personio.com Serbien",
    "site:jobs.personio.com Ukraine",
    "site:jobs.personio.com Israel",
    "site:jobs.personio.com USA",
    "site:jobs.personio.com America",
    "site:jobs.personio.com United States",
    "site:jobs.personio.com Canada",
    "site:jobs.personio.com Kanada",
    "site:jobs.personio.com Singapore",
    "site:jobs.personio.com Singapur",
    "site:jobs.personio.com Australia",
    "site:jobs.personio.com Australien",
    "site:jobs.personio.com New Zealand",
    "site:jobs.personio.com Japan",
    "site:jobs.personio.com South Korea",
    "site:jobs.personio.com Korea",
    "site:jobs.personio.com China",
    "site:jobs.personio.com Hong Kong",
    "site:jobs.personio.com Taiwan",
    "site:jobs.personio.com India",
    "site:jobs.personio.com Indien",
    "site:jobs.personio.com Philippines",
    "site:jobs.personio.com Vietnam",
    "site:jobs.personio.com Thailand",
    "site:jobs.personio.com Indonesia",
    "site:jobs.personio.com Malaysia",
    "site:jobs.personio.com Mexico",
    "site:jobs.personio.com Mexiko",
    "site:jobs.personio.com Brazil",
    "site:jobs.personio.com Brasilien",
    "site:jobs.personio.com Argentina",
    "site:jobs.personio.com Chile",
    "site:jobs.personio.com Colombia",
    "site:jobs.personio.com South Africa",
    "site:jobs.personio.com Südafrika",
    "site:jobs.personio.com Nigeria",
    "site:jobs.personio.com Kenya",
    "site:jobs.personio.com Egypt",
    "site:jobs.personio.com Morocco",
    "site:jobs.personio.com UAE",
    "site:jobs.personio.com Dubai",
    "site:jobs.personio.com Saudi Arabia",
    "site:jobs.personio.com Qatar",
    "site:jobs.personio.com Turkey",
    "site:jobs.personio.com Türkei",
    # Cities - Major European cities
    "site:jobs.personio.com Berlin",
    "site:jobs.personio.com Munich",
    "site:jobs.personio.com München",
    "site:jobs.personio.com Hamburg",
    "site:jobs.personio.com Frankfurt",
    "site:jobs.personio.com Cologne",
    "site:jobs.personio.com Köln",
    "site:jobs.personio.com Düsseldorf",
    "site:jobs.personio.com Stuttgart",
    "site:jobs.personio.com Dresden",
    "site:jobs.personio.com Leipzig",
    "site:jobs.personio.com Hannover",
    "site:jobs.personio.com Hanover",
    "site:jobs.personio.com Nuremberg",
    "site:jobs.personio.com Nürnberg",
    "site:jobs.personio.com Dortmund",
    "site:jobs.personio.com Essen",
    "site:jobs.personio.com Bremen",
    "site:jobs.personio.com Bonn",
    "site:jobs.personio.com Mannheim",
    "site:jobs.personio.com Karlsruhe",
    "site:jobs.personio.com Freiburg",
    "site:jobs.personio.com Heidelberg",
    "site:jobs.personio.com Aachen",
    "site:jobs.personio.com Mainz",
    "site:jobs.personio.com Wiesbaden",
    "site:jobs.personio.com Augsburg",
    "site:jobs.personio.com Regensburg",
    "site:jobs.personio.com Ulm",
    "site:jobs.personio.com Bielefeld",
    "site:jobs.personio.com Münster",
    "site:jobs.personio.com Kiel",
    "site:jobs.personio.com Rostock",
    "site:jobs.personio.com Potsdam",
    "site:jobs.personio.com Vienna",
    "site:jobs.personio.com Wien",
    "site:jobs.personio.com Graz",
    "site:jobs.personio.com Salzburg",
    "site:jobs.personio.com Linz",
    "site:jobs.personio.com Innsbruck",
    "site:jobs.personio.com Zurich",
    "site:jobs.personio.com Zürich",
    "site:jobs.personio.com Geneva",
    "site:jobs.personio.com Genf",
    "site:jobs.personio.com Basel",
    "site:jobs.personio.com Bern",
    "site:jobs.personio.com Lausanne",
    "site:jobs.personio.com Lugano",
    "site:jobs.personio.com Amsterdam",
    "site:jobs.personio.com Rotterdam",
    "site:jobs.personio.com The Hague",
    "site:jobs.personio.com Den Haag",
    "site:jobs.personio.com Utrecht",
    "site:jobs.personio.com Eindhoven",
    "site:jobs.personio.com Brussels",
    "site:jobs.personio.com Brüssel",
    "site:jobs.personio.com Antwerp",
    "site:jobs.personio.com Ghent",
    "site:jobs.personio.com Paris",
    "site:jobs.personio.com Lyon",
    "site:jobs.personio.com Marseille",
    "site:jobs.personio.com Toulouse",
    "site:jobs.personio.com Bordeaux",
    "site:jobs.personio.com Lille",
    "site:jobs.personio.com Nantes",
    "site:jobs.personio.com Nice",
    "site:jobs.personio.com Strasbourg",
    "site:jobs.personio.com Madrid",
    "site:jobs.personio.com Barcelona",
    "site:jobs.personio.com Valencia",
    "site:jobs.personio.com Seville",
    "site:jobs.personio.com Bilbao",
    "site:jobs.personio.com Malaga",
    "site:jobs.personio.com Lisbon",
    "site:jobs.personio.com Lissabon",
    "site:jobs.personio.com Porto",
    "site:jobs.personio.com Milan",
    "site:jobs.personio.com Mailand",
    "site:jobs.personio.com Rome",
    "site:jobs.personio.com Rom",
    "site:jobs.personio.com Turin",
    "site:jobs.personio.com Florence",
    "site:jobs.personio.com Florenz",
    "site:jobs.personio.com Bologna",
    "site:jobs.personio.com Naples",
    "site:jobs.personio.com London",
    "site:jobs.personio.com Manchester",
    "site:jobs.personio.com Birmingham",
    "site:jobs.personio.com Leeds",
    "site:jobs.personio.com Bristol",
    "site:jobs.personio.com Edinburgh",
    "site:jobs.personio.com Glasgow",
    "site:jobs.personio.com Cambridge",
    "site:jobs.personio.com Oxford",
    "site:jobs.personio.com Dublin",
    "site:jobs.personio.com Cork",
    "site:jobs.personio.com Galway",
    "site:jobs.personio.com Warsaw",
    "site:jobs.personio.com Warschau",
    "site:jobs.personio.com Krakow",
    "site:jobs.personio.com Kraków",
    "site:jobs.personio.com Wroclaw",
    "site:jobs.personio.com Gdansk",
    "site:jobs.personio.com Poznan",
    "site:jobs.personio.com Prague",
    "site:jobs.personio.com Prag",
    "site:jobs.personio.com Brno",
    "site:jobs.personio.com Stockholm",
    "site:jobs.personio.com Gothenburg",
    "site:jobs.personio.com Malmö",
    "site:jobs.personio.com Copenhagen",
    "site:jobs.personio.com Kopenhagen",
    "site:jobs.personio.com Oslo",
    "site:jobs.personio.com Bergen",
    "site:jobs.personio.com Helsinki",
    "site:jobs.personio.com Espoo",
    "site:jobs.personio.com Budapest",
    "site:jobs.personio.com Bucharest",
    "site:jobs.personio.com Bukarest",
    "site:jobs.personio.com Athens",
    "site:jobs.personio.com Athen",
    "site:jobs.personio.com Sofia",
    "site:jobs.personio.com Belgrade",
    "site:jobs.personio.com Belgrad",
    "site:jobs.personio.com Zagreb",
    "site:jobs.personio.com Ljubljana",
    "site:jobs.personio.com Bratislava",
    "site:jobs.personio.com Tallinn",
    "site:jobs.personio.com Riga",
    "site:jobs.personio.com Vilnius",
    "site:jobs.personio.com Kyiv",
    "site:jobs.personio.com Kiew",
    "site:jobs.personio.com Tel Aviv",
    "site:jobs.personio.com Istanbul",
    "site:jobs.personio.com New York",
    "site:jobs.personio.com San Francisco",
    "site:jobs.personio.com Los Angeles",
    "site:jobs.personio.com Boston",
    "site:jobs.personio.com Chicago",
    "site:jobs.personio.com Austin",
    "site:jobs.personio.com Seattle",
    "site:jobs.personio.com Denver",
    "site:jobs.personio.com Miami",
    "site:jobs.personio.com Atlanta",
    "site:jobs.personio.com Washington",
    "site:jobs.personio.com Toronto",
    "site:jobs.personio.com Montreal",
    "site:jobs.personio.com Vancouver",
    "site:jobs.personio.com Sydney",
    "site:jobs.personio.com Melbourne",
    "site:jobs.personio.com Tokyo",
    "site:jobs.personio.com Seoul",
    "site:jobs.personio.com Shanghai",
    "site:jobs.personio.com Beijing",
    "site:jobs.personio.com Shenzhen",
    "site:jobs.personio.com Bangalore",
    "site:jobs.personio.com Mumbai",
    "site:jobs.personio.com Delhi",
    "site:jobs.personio.com Hyderabad",
    # Job roles
    "site:jobs.personio.com engineer",
    "site:jobs.personio.com developer",
    "site:jobs.personio.com programmer",
    "site:jobs.personio.com coder",
    "site:jobs.personio.com backend",
    "site:jobs.personio.com frontend",
    "site:jobs.personio.com fullstack",
    "site:jobs.personio.com full-stack",
    "site:jobs.personio.com devops",
    "site:jobs.personio.com SRE",
    "site:jobs.personio.com platform engineer",
    "site:jobs.personio.com cloud engineer",
    "site:jobs.personio.com data scientist",
    "site:jobs.personio.com data analyst",
    "site:jobs.personio.com data engineer",
    "site:jobs.personio.com ML engineer",
    "site:jobs.personio.com AI engineer",
    "site:jobs.personio.com product manager",
    "site:jobs.personio.com product owner",
    "site:jobs.personio.com project manager",
    "site:jobs.personio.com program manager",
    "site:jobs.personio.com scrum master",
    "site:jobs.personio.com agile coach",
    "site:jobs.personio.com designer",
    "site:jobs.personio.com UX designer",
    "site:jobs.personio.com UI designer",
    "site:jobs.personio.com graphic designer",
    "site:jobs.personio.com product designer",
    "site:jobs.personio.com marketing manager",
    "site:jobs.personio.com content manager",
    "site:jobs.personio.com social media",
    "site:jobs.personio.com SEO",
    "site:jobs.personio.com performance marketing",
    "site:jobs.personio.com growth",
    "site:jobs.personio.com sales manager",
    "site:jobs.personio.com account executive",
    "site:jobs.personio.com account manager",
    "site:jobs.personio.com business development",
    "site:jobs.personio.com BDR",
    "site:jobs.personio.com SDR",
    "site:jobs.personio.com customer success",
    "site:jobs.personio.com customer support",
    "site:jobs.personio.com customer service",
    "site:jobs.personio.com HR manager",
    "site:jobs.personio.com recruiter",
    "site:jobs.personio.com talent acquisition",
    "site:jobs.personio.com people operations",
    "site:jobs.personio.com finance manager",
    "site:jobs.personio.com controller",
    "site:jobs.personio.com accountant",
    "site:jobs.personio.com CFO",
    "site:jobs.personio.com treasurer",
    "site:jobs.personio.com operations manager",
    "site:jobs.personio.com COO",
    "site:jobs.personio.com office manager",
    "site:jobs.personio.com analyst",
    "site:jobs.personio.com consultant",
    "site:jobs.personio.com manager",
    "site:jobs.personio.com director",
    "site:jobs.personio.com head of",
    "site:jobs.personio.com VP",
    "site:jobs.personio.com vice president",
    "site:jobs.personio.com C-level",
    "site:jobs.personio.com CTO",
    "site:jobs.personio.com CEO",
    "site:jobs.personio.com CMO",
    "site:jobs.personio.com CPO",
    "site:jobs.personio.com intern",
    "site:jobs.personio.com internship",
    "site:jobs.personio.com praktikum",
    "site:jobs.personio.com werkstudent",
    "site:jobs.personio.com working student",
    "site:jobs.personio.com trainee",
    "site:jobs.personio.com ausbildung",
    "site:jobs.personio.com apprentice",
    "site:jobs.personio.com graduate",
    "site:jobs.personio.com junior",
    "site:jobs.personio.com senior",
    "site:jobs.personio.com lead",
    "site:jobs.personio.com principal",
    "site:jobs.personio.com staff",
    "site:jobs.personio.com architect",
    "site:jobs.personio.com team lead",
    "site:jobs.personio.com engineering manager",
    # Work arrangements
    "site:jobs.personio.com remote",
    "site:jobs.personio.com remote work",
    "site:jobs.personio.com work from home",
    "site:jobs.personio.com hybrid",
    "site:jobs.personio.com home office",
    "site:jobs.personio.com homeoffice",
    "site:jobs.personio.com full-time",
    "site:jobs.personio.com vollzeit",
    "site:jobs.personio.com part-time",
    "site:jobs.personio.com teilzeit",
    "site:jobs.personio.com freelance",
    "site:jobs.personio.com contract",
    "site:jobs.personio.com temporary",
    "site:jobs.personio.com befristet",
    "site:jobs.personio.com permanent",
    "site:jobs.personio.com unbefristet",
    # Technologies
    "site:jobs.personio.com Python",
    "site:jobs.personio.com Java",
    "site:jobs.personio.com JavaScript",
    "site:jobs.personio.com TypeScript",
    "site:jobs.personio.com React",
    "site:jobs.personio.com Angular",
    "site:jobs.personio.com Vue",
    "site:jobs.personio.com Node.js",
    "site:jobs.personio.com Express",
    "site:jobs.personio.com Django",
    "site:jobs.personio.com Flask",
    "site:jobs.personio.com Spring",
    "site:jobs.personio.com .NET",
    "site:jobs.personio.com C#",
    "site:jobs.personio.com Go",
    "site:jobs.personio.com Golang",
    "site:jobs.personio.com Rust",
    "site:jobs.personio.com C++",
    "site:jobs.personio.com C",
    "site:jobs.personio.com Ruby",
    "site:jobs.personio.com Rails",
    "site:jobs.personio.com PHP",
    "site:jobs.personio.com Laravel",
    "site:jobs.personio.com Kotlin",
    "site:jobs.personio.com Swift",
    "site:jobs.personio.com iOS",
    "site:jobs.personio.com Android",
    "site:jobs.personio.com mobile",
    "site:jobs.personio.com React Native",
    "site:jobs.personio.com Flutter",
    "site:jobs.personio.com AWS",
    "site:jobs.personio.com Azure",
    "site:jobs.personio.com GCP",
    "site:jobs.personio.com Google Cloud",
    "site:jobs.personio.com Kubernetes",
    "site:jobs.personio.com K8s",
    "site:jobs.personio.com Docker",
    "site:jobs.personio.com Terraform",
    "site:jobs.personio.com Ansible",
    "site:jobs.personio.com Jenkins",
    "site:jobs.personio.com CI/CD",
    "site:jobs.personio.com GitLab",
    "site:jobs.personio.com GitHub",
    "site:jobs.personio.com PostgreSQL",
    "site:jobs.personio.com MySQL",
    "site:jobs.personio.com MongoDB",
    "site:jobs.personio.com Redis",
    "site:jobs.personio.com Elasticsearch",
    "site:jobs.personio.com Kafka",
    "site:jobs.personio.com RabbitMQ",
    "site:jobs.personio.com GraphQL",
    "site:jobs.personio.com REST API",
    "site:jobs.personio.com microservices",
    "site:jobs.personio.com Salesforce",
    "site:jobs.personio.com SAP",
    "site:jobs.personio.com Oracle",
    "site:jobs.personio.com Microsoft",
    "site:jobs.personio.com Power BI",
    "site:jobs.personio.com Tableau",
    "site:jobs.personio.com Snowflake",
    "site:jobs.personio.com Databricks",
    "site:jobs.personio.com Spark",
    "site:jobs.personio.com Hadoop",
    "site:jobs.personio.com TensorFlow",
    "site:jobs.personio.com PyTorch",
    "site:jobs.personio.com Figma",
    "site:jobs.personio.com Sketch",
    "site:jobs.personio.com Adobe",
    "site:jobs.personio.com HubSpot",
    "site:jobs.personio.com Shopify",
    "site:jobs.personio.com Magento",
    # German job posting keywords
    "site:jobs.personio.com Stelle",
    "site:jobs.personio.com Stellenangebot",
    "site:jobs.personio.com Karriere",
    "site:jobs.personio.com Bewerbung",
    "site:jobs.personio.com Mitarbeiter",
    "site:jobs.personio.com Festanstellung",
    "site:jobs.personio.com Berufserfahrung",
    "site:jobs.personio.com Einstieg",
    "site:jobs.personio.com Quereinsteiger",
    # Alphabetical subdomain exploration
    "site:jobs.personio.com a",
    "site:jobs.personio.com b",
    "site:jobs.personio.com c",
    "site:jobs.personio.com d",
    "site:jobs.personio.com e",
    "site:jobs.personio.com f",
    "site:jobs.personio.com g",
    "site:jobs.personio.com h",
    "site:jobs.personio.com i",
    "site:jobs.personio.com j",
    "site:jobs.personio.com k",
    "site:jobs.personio.com l",
    "site:jobs.personio.com m",
    "site:jobs.personio.com n",
    "site:jobs.personio.com o",
    "site:jobs.personio.com p",
    "site:jobs.personio.com q",
    "site:jobs.personio.com r",
    "site:jobs.personio.com s",
    "site:jobs.personio.com t",
    "site:jobs.personio.com u",
    "site:jobs.personio.com v",
    "site:jobs.personio.com w",
    "site:jobs.personio.com x",
    "site:jobs.personio.com y",
    "site:jobs.personio.com z",
    "site:jobs.personio.com 1",
    "site:jobs.personio.com 2",
    "site:jobs.personio.com 3",
    "site:jobs.personio.com 4",
    "site:jobs.personio.com 5",
    "site:jobs.personio.com 0",
    # Common company name patterns
    "site:jobs.personio.com solutions",
    "site:jobs.personio.com systems",
    "site:jobs.personio.com services",
    "site:jobs.personio.com group",
    "site:jobs.personio.com holding",
    "site:jobs.personio.com international",
    "site:jobs.personio.com global",
    "site:jobs.personio.com europe",
    "site:jobs.personio.com labs",
    "site:jobs.personio.com studio",
    "site:jobs.personio.com works",
    "site:jobs.personio.com hub",
    "site:jobs.personio.com ventures",
    "site:jobs.personio.com capital",
    "site:jobs.personio.com partners",
    "site:jobs.personio.com team",
    "site:jobs.personio.com collective",
    "site:jobs.personio.com factory",
    "site:jobs.personio.com network",
    "site:jobs.personio.com technologies",
    "site:jobs.personio.com innovations",
    "site:jobs.personio.com digital",
    # Year-based searches (for recently founded companies)
    "site:jobs.personio.com 2024",
    "site:jobs.personio.com 2023",
    "site:jobs.personio.com 2022",
    "site:jobs.personio.com founded",
    "site:jobs.personio.com new company",
    # Funding stage searches
    "site:jobs.personio.com series A",
    "site:jobs.personio.com series B",
    "site:jobs.personio.com series C",
    "site:jobs.personio.com seed",
    "site:jobs.personio.com funded",
    "site:jobs.personio.com backed",
    # Alternative search patterns
    '"*.site:jobs.personio.com"',
    "allinurl:site:jobs.personio.com",
    "personio karriere",
    "personio stellenangebote",
    "personio jobs portal",
    "personio career page",
    "personio hiring",
    "work at * personio",
    "careers * personio",
]


def search_searxng(query: str, searxng_url: str, page: int = 1) -> list:
    """Execute a search query on SearXNG and return results."""
    encoded_query = urllib.parse.quote(query)
    url = f"{searxng_url}/search?q={encoded_query}&format=json&pageno={page}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data.get("results", [])
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  Error searching for '{query}': {e}")
        return []


def extract_subdomain(url: str) -> str | None:
    """Extract the subdomain from a Personio jobs URL."""
    match = re.search(r"https?://([^.]+)\.jobs\.personio\.com", url)
    return match.group(1) if match else None


def clean_company_name(subdomain: str) -> str:
    """Convert subdomain to a readable company name."""
    # Remove common suffixes
    name = subdomain
    suffixes = [
        "-gmbh",
        "-ag",
        "-se",
        "-ltd",
        "-inc",
        "-bv",
        "-1",
        "-2",
        "-3",
        "-latest",
        "-careers",
        "-jobs",
        "-de",
        "-eu",
        "-int",
        "-group",
        "-holding",
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]

    # Replace dashes with spaces and title case
    name = name.replace("-", " ").title()

    # Fix common abbreviations
    abbreviations = {
        " Gmbh": " GmbH",
        " Ag": " AG",
        " Se": " SE",
        " Kg": " KG",
        " Bv": " BV",
        " Uk": " UK",
        " Eu": " EU",
        " Us": " US",
        " Ai": " AI",
        " Io": " IO",
        " It": " IT",
        " Hr": " HR",
        " Rd": " R&D",
        " Iot": " IoT",
        " Nft": " NFT",
        " Srl": " Srl",
        " Sarl": " SARL",
        " Sas": " SAS",
    }
    for old, new in abbreviations.items():
        name = name.replace(old, new)

    return name


def load_existing_companies(csv_path: Path) -> Set[str]:
    """Load existing company subdomains from CSV."""
    subdomains = set()
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                subdomain = extract_subdomain(row.get("url", ""))
                if subdomain:
                    subdomains.add(subdomain)
    return subdomains


def save_companies(companies: dict, csv_path: Path):
    """Save all companies to CSV."""
    sorted_companies = sorted(companies.values(), key=lambda c: c.name.lower())

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "url"])
        for company in sorted_companies:
            writer.writerow([company.name, company.url])

    print(f"\nSaved {len(sorted_companies)} companies to {csv_path}")


def discover_companies(
    searxng_url: str, csv_path: Path, delay: float = 1.0, pages: int = 1
):
    """Main discovery function."""
    print(f"Starting Personio company discovery...")
    print(f"SearXNG URL: {searxng_url}")
    print(f"Output file: {csv_path}")
    print(f"Search queries: {len(SEARCH_QUERIES)}")
    print(f"Pages per query: {pages}")
    print("-" * 60)

    # Load existing companies
    existing_subdomains = load_existing_companies(csv_path)
    print(f"Existing companies: {len(existing_subdomains)}")

    # Track all companies
    companies = {}

    # Load existing into companies dict
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                subdomain = extract_subdomain(row.get("url", ""))
                if subdomain:
                    companies[subdomain] = Company(
                        name=row["name"], url=row["url"], subdomain=subdomain
                    )

    initial_count = len(companies)
    new_count = 0

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{len(SEARCH_QUERIES)}] Searching: {query}")

        query_new = 0

        for page in range(1, pages + 1):
            results = search_searxng(query, searxng_url, page)

            for result in results:
                url = result.get("url", "")
                subdomain = extract_subdomain(url)

                if subdomain and subdomain not in companies:
                    clean_url = f"https://{subdomain}.site:jobs.personio.com"
                    name = clean_company_name(subdomain)

                    companies[subdomain] = Company(
                        name=name, url=clean_url, subdomain=subdomain
                    )
                    query_new += 1
                    new_count += 1

            if page < pages:
                time.sleep(delay / 2)  # Shorter delay between pages

        if query_new > 0:
            print(f"  Found {query_new} new companies (total: {len(companies)})")

        # Save periodically every 25 queries
        if i % 25 == 0:
            save_companies(companies, csv_path)

        # Rate limiting
        time.sleep(delay)

    # Final save
    save_companies(companies, csv_path)

    print("\n" + "=" * 60)
    print(f"Discovery complete!")
    print(f"Total companies found: {len(companies)}")
    print(f"New companies added: {new_count}")
    print(f"Growth: {initial_count} -> {len(companies)} ({new_count} new)")


def main():
    parser = argparse.ArgumentParser(
        description="Discover companies using Personio for job postings"
    )
    parser.add_argument(
        "--searxng-url",
        default="http://127.0.0.1:8888",
        help="SearXNG instance URL (default: http://127.0.0.1:8888)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV file path (default: personio_companies.csv in same directory)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between searches in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of result pages to fetch per query (default: 1)",
    )

    args = parser.parse_args()

    # Determine output path
    if args.output:
        csv_path = Path(args.output)
    else:
        csv_path = Path(__file__).parent / "personio_companies.csv"

    discover_companies(args.searxng_url, csv_path, args.delay, args.pages)


if __name__ == "__main__":
    main()
