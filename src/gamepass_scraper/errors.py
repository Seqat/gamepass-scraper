"""Exception types raised by the scraper."""


class ScraperError(Exception):
    """Base class for expected, user-facing failures."""


class SourceError(ScraperError):
    """A data source could not be reached or returned unusable data."""
