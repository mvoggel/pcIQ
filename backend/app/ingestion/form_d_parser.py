"""
Form D XML parser.

Takes the raw XML string from EDGAR and returns a FormDFiling model.

Form D XML schema reference:
  https://www.sec.gov/info/edgar/edgarfm-vol2-v59.pdf (Chapter 8)

Key XML paths:
  primaryIssuer/entityName
  primaryIssuer/issuerAddress/{street1,city,stateOrCountry,zipCode}
  offeringData/industryGroup/industryGroupType
  offeringData/industryGroup/investmentFundInfo/investmentFundType
  offeringData/typeOfFiling/dateOfFirstSale
  offeringData/offeringSalesAmounts/{totalOfferingAmount,totalAmountSold}
  offeringData/investors/totalNumberAlreadyInvested
  relatedPersonsList/relatedPersonInfo/...
  offeringData/salesCompensationList/recipient/{recipientName,recipientCRDNumber,
    statesOfSolicitationList/state}
"""

import xml.etree.ElementTree as ET
from datetime import date

from app.models.form_d import (
    FormDFiling,
    IssuerAddress,
    OfferingAmounts,
    RelatedPerson,
    SalesCompensationRecipient,
)


def _text(element: ET.Element | None, path: str, default: str = "") -> str:
    if element is None:
        return default
    node = element.find(path)
    return (node.text or "").strip() if node is not None else default


def _date(element: ET.Element | None, path: str) -> date | None:
    raw = _text(element, path)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _float(element: ET.Element | None, path: str) -> float | None:
    raw = _text(element, path)
    if not raw or raw == "Indefinite":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int(element: ET.Element | None, path: str) -> int | None:
    raw = _text(element, path)
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def parse_form_d(xml_str: str, cik: str, accession_no: str) -> FormDFiling:
    """
    Parse a Form D XML document into a FormDFiling model.

    Args:
        xml_str:      Raw XML string from EDGAR
        cik:          Issuer CIK (10-digit, zero-padded)
        accession_no: Filing accession number (e.g. 0001234567-26-000001)

    Returns:
        Populated FormDFiling instance. Invalid/missing fields default to
        empty strings or None rather than raising.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Form D XML for {cik}/{accession_no}: {exc}") from exc

    # --- Issuer ---
    issuer = root.find("primaryIssuer")
    entity_name = _text(issuer, "entityName")
    phone = _text(issuer, "phone")

    addr_el = issuer.find("issuerAddress") if issuer is not None else None
    address = IssuerAddress(
        street1=_text(addr_el, "street1"),
        street2=_text(addr_el, "street2"),
        city=_text(addr_el, "city"),
        state_or_country=_text(addr_el, "stateOrCountry"),
        zip_code=_text(addr_el, "zipCode"),
    )

    # --- Related persons ---
    related_persons: list[RelatedPerson] = []
    for rp in root.findall(".//relatedPersonInfo"):
        name_el = rp.find("relatedPersonName")
        relationships = [
            rel.text.strip()
            for rel in rp.findall(".//relationship")
            if rel.text
        ]
        related_persons.append(
            RelatedPerson(
                first_name=_text(name_el, "firstName"),
                last_name=_text(name_el, "lastName"),
                relationship=relationships,
            )
        )

    # --- Offering data ---
    offering = root.find("offeringData")

    industry_group = offering.find("industryGroup") if offering is not None else None
    industry_group_type = _text(industry_group, "industryGroupType")
    investment_fund_type = _text(industry_group, "investmentFundInfo/investmentFundType")

    type_of_filing = offering.find("typeOfFiling") if offering is not None else None
    is_amendment = _text(type_of_filing, "newOrAmendment").lower() == "amendment"
    date_of_first_sale = _date(type_of_filing, "dateOfFirstSale")

    sales_amounts = offering.find("offeringSalesAmounts") if offering is not None else None
    offering_amounts = OfferingAmounts(
        total_offering_amount=_float(sales_amounts, "totalOfferingAmount"),
        total_amount_sold=_float(sales_amounts, "totalAmountSold"),
        total_remaining=_float(sales_amounts, "totalRemaining"),
    )

    investors = offering.find("investors") if offering is not None else None
    total_investors = _int(investors, "totalNumberAlreadyInvested")
    has_non_accredited = _text(investors, "hasNonAccreditedInvestors").lower() == "true"

    # Federal exemptions (e.g. "06b" = Rule 506(b))
    federal_exemptions = [
        el.text.strip()
        for el in root.findall(".//federalExemptionsExclusions/item")
        if el.text
    ]

    # --- Sales compensation recipients (distribution platforms / BDs) ---
    sales_recipients = _parse_sales_recipients(offering)

    return FormDFiling(
        cik=cik,
        accession_no=accession_no,
        entity_name=entity_name,
        address=address,
        phone=phone,
        related_persons=related_persons,
        sales_recipients=sales_recipients,
        industry_group_type=industry_group_type,
        investment_fund_type=investment_fund_type,
        is_amendment=is_amendment,
        date_of_first_sale=date_of_first_sale,
        offering=offering_amounts,
        total_investors=total_investors,
        has_non_accredited_investors=has_non_accredited,
        federal_exemptions=federal_exemptions,
    )


def _parse_sales_recipients(offering: ET.Element | None) -> list[SalesCompensationRecipient]:
    """
    Extract all broker-dealer / platform recipients from salesCompensationList.

    XML structure (confirmed from live filings):
      <salesCompensationList>
        <recipient>
          <recipientName>iCapital Securities LLC</recipientName>
          <recipientCRDNumber>12345</recipientCRDNumber>
          <associatedBDName>...</associatedBDName>
          <recipientAddress>
            <city>NEW YORK</city>
            <stateOrCountry>NY</stateOrCountry>
          </recipientAddress>
          <statesOfSolicitationList>
            <state>NY</state>
            <state>CA</state>
          </statesOfSolicitationList>
          <foreignSolicitation>false</foreignSolicitation>
        </recipient>
      </salesCompensationList>

    Note: "None" appears as a literal string in some fields — we treat it as empty.
    """
    if offering is None:
        return []

    recipients: list[SalesCompensationRecipient] = []
    for rec in offering.findall(".//salesCompensationList/recipient"):
        name = _text(rec, "recipientName")
        if not name or name.lower() == "none":
            continue

        crd = _text(rec, "recipientCRDNumber")
        if crd.lower() == "none":
            crd = ""

        bd_name = _text(rec, "associatedBDName")
        if bd_name.lower() == "none":
            bd_name = ""

        addr = rec.find("recipientAddress")
        city  = _text(addr, "city").title()
        state = _text(addr, "stateOrCountry").upper()

        # States of solicitation — list of <state>XX</state> elements
        sol_list = rec.find("statesOfSolicitationList")
        states: list[str] = []
        all_states = False
        if sol_list is not None:
            for s in sol_list.findall("state"):
                val = (s.text or "").strip().upper()
                if val in ("54", "ALL"):       # "54" = all US jurisdictions in EDGAR
                    all_states = True
                    break
                if len(val) == 2:
                    states.append(val)

        recipients.append(SalesCompensationRecipient(
            name=name,
            crd_number=crd,
            associated_bd_name=bd_name,
            city=city,
            state_or_country=state,
            states_of_solicitation=states,
            all_states=all_states,
        ))

    return recipients
