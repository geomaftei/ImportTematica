"""Excepțiile procesului - echivalentul BusinessRuleException / System.Exception din REFramework."""


class BusinessRuleException(Exception):
    """Tranzacția este invalidă (ex. matricea nu respectă template-ul). Nu se reîncearcă."""


class ApplicationException(Exception):
    """Eroare tehnică (aplicația nu răspunde, selector negăsit etc.). Se poate reîncerca."""
